"""Document ingestion: register version -> chunk -> embed -> vectors -> summary
-> publish after the fence/provenance check. Idempotent on retry (deterministic
chunk artifact IDs make re-runs safe upserts)."""
from __future__ import annotations

import hashlib
import uuid as uuidlib

from sqlalchemy.orm import Session

from .chunking import chunk_text, split_sentences, token_overlap
from .config import Settings
from .connectors.qdrant_c import QdrantConnector
from .errors import PublicationBlocked
from .fence import current_fence_generation, gate_publish
from .jobs import schedule_job
from .models import (
    Artifact,
    ArtifactType,
    Claim,
    ClaimStatus,
    ClaimSupport,
    Document,
    DocumentState,
    DocumentVersion,
    JobType,
    LifecycleState,
    Relationship,
    Summary,
    WriteIntent,
    utcnow,
)
from .provenance import register_artifact, register_edge

_NS = uuidlib.UUID("7a3c1c2e-5f4a-4b8e-9a2d-1e0f6b7c9d01")
SUPPORT_OVERLAP_THRESHOLD = 0.75


def create_document(
    db: Session,
    *,
    workspace_id: int,
    title: str,
    content: str,
    source_type: str = "txt",
    filename: str = "",
) -> Document:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    doc = Document(workspace_id=workspace_id, title=title[:512],
                   state=DocumentState.active.value)
    db.add(doc)
    db.flush()
    version = DocumentVersion(
        document_id=doc.id, version=1, source_type=source_type,
        filename=filename[:512], content=content, checksum=checksum,
    )
    db.add(version)
    db.flush()
    doc.current_version_id = version.id
    register_artifact(
        db,
        workspace_id=workspace_id,
        type=ArtifactType.document_version,
        document_id=doc.id,
        document_version_id=version.id,
        version=1,
        meta={"version": 1, "checksum": checksum, "source_type": source_type,
              "char_count": len(content)},
    )
    schedule_job(db, JobType.ingest, {"document_id": str(doc.id)})
    db.commit()
    return doc


def _chunk_artifact_id(version_artifact_id: uuidlib.UUID, index: int) -> uuidlib.UUID:
    return uuidlib.uuid5(_NS, f"chunk:{version_artifact_id}:{index}")


def _build_summary_text(settings: Settings, llm, content: str) -> str:
    """Extractive summary (deterministic). The LLM path is intentionally NOT
    used for stored summaries in this prototype so claim support stays exact."""
    from .chunking import split_sentences as _s

    sentences = _s(content)
    if not sentences:
        return content[:600]
    # rank by position-weighted length: lead + informative
    picked = sentences[: min(4, len(sentences))]
    return " ".join(s["text"] for s in picked)


def process_ingestion(
    db: Session,
    settings: Settings,
    *,
    document_id: uuidlib.UUID,
    embedding,
    llm,
    qdrant: QdrantConnector,
) -> dict:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    if doc.state == DocumentState.deleted.value:
        return {"status": "skipped_deleted", "chunks": 0, "vectors": 0}
    version = db.get(DocumentVersion, doc.current_version_id)
    version_artifact = (
        db.query(Artifact)
        .filter_by(document_version_id=version.id, type=ArtifactType.document_version)
        .one()
    )

    # Idempotency: chunks already registered for this version => retry after
    # partial completion just re-upserts the same deterministic IDs.
    existing_chunks = (
        db.query(Artifact)
        .filter_by(document_version_id=version.id, type=ArtifactType.chunk)
        .count()
    )
    if existing_chunks > 0:
        return {"status": "already_ingested", "chunks": existing_chunks}

    pieces = chunk_text(version.content)
    fence = current_fence_generation(db, doc.workspace_id)

    # ---- chunk artifacts + edges
    chunk_rows: list[Artifact] = []
    for piece in pieces:
        art = register_artifact(
            db,
            workspace_id=doc.workspace_id,
            type=ArtifactType.chunk,
            document_id=doc.id,
            document_version_id=version.id,
            locator={"kind": "postgres"},
            meta={"index": piece["index"], "start": piece["start"],
                  "end": piece["end"], "text": piece["text"]},
            artifact_id=_chunk_artifact_id(version_artifact.id, piece["index"]),
        )
        register_edge(db, parent=version_artifact, child=art,
                      relationship=Relationship.contains,
                      source_version=version.version)
        chunk_rows.append(art)

    # ---- vectors (staged via write intent)
    qdrant.ensure_collection()
    points = []
    if chunk_rows:
        vectors = embedding.embed([p["text"] for p in pieces])
        for art, piece, vec in zip(chunk_rows, pieces, vectors):
            points.append({
                "id": str(art.id),
                "vector": vec,
                "payload": {
                    "workspace_id": doc.workspace_id,
                    "document_id": str(doc.id),
                    "document_version_id": str(version.id),
                    "artifact_id": str(art.id),
                    "type": "chunk",
                    "chunk_index": piece["index"],
                    "fence_epoch": fence,
                },
            })
    intent = WriteIntent(
        workspace_id=doc.workspace_id, artifact_id=version_artifact.id,
        connector="qdrant", fence_epoch=fence,
        payload={"point_ids": [p["id"] for p in points]},
    )
    db.add(intent)
    db.flush()
    outcome = qdrant.upsert_points(points)
    if not outcome.ok:
        db.rollback()
        from .errors import ConnectorUnavailable

        raise ConnectorUnavailable(
            f"Qdrant upsert failed ({outcome.error_code}); job stays queued for retry."
        )

    # ---- optional registered summary with claim supports
    summary_text = _build_summary_text(settings, llm, version.content)
    summary_artifact = register_artifact(
        db, workspace_id=doc.workspace_id, type=ArtifactType.summary,
        document_id=doc.id, document_version_id=version.id,
        meta={"summary_version": 1, "mode": "extractive"},
    )
    summary_row = Summary(artifact_id=summary_artifact.id, content=summary_text,
                          summary_version=1)
    db.add(summary_row)
    register_edge(db, parent=version_artifact, child=summary_artifact,
                  relationship=Relationship.summarizes, source_version=version.version)
    for i, claim in enumerate(split_sentences(summary_text)):
        best, best_score = None, 0.0
        for art, piece in zip(chunk_rows, pieces):
            score = token_overlap(claim["text"], piece["text"])
            if score > best_score:
                best, best_score = (art, piece), score
        row = Claim(summary_artifact_id=summary_artifact.id, idx=i,
                    text=claim["text"],
                    status=ClaimStatus.pending.value)
        db.add(row)
        db.flush()
        if best is not None and best_score >= SUPPORT_OVERLAP_THRESHOLD:
            row.status = ClaimStatus.supported.value
            db.add(ClaimSupport(
                claim_id=row.id, source_artifact_id=best[0].id,
                document_id=doc.id, source_version=version.version,
                offsets={"start": best[1]["start"], "end": best[1]["end"]},
            ))
            register_edge(db, parent=best[0], child=summary_artifact,
                          relationship=Relationship.supports)
        else:
            row.status = ClaimStatus.uncertain.value

    # ---- fence gate, then publish
    try:
        gate_publish(db, doc.workspace_id, [doc.id])
    except PublicationBlocked:
        # Deletion committed first: clean staged external writes, never publish.
        qdrant.delete_points([p["id"] for p in points])
        for art in chunk_rows:
            art.lifecycle_state = LifecycleState.removed.value
        summary_artifact.lifecycle_state = LifecycleState.removed.value
        summary_row.content_state = "removed"
        db.commit()
        raise
    intent.state = "published"
    intent.settled_at = utcnow()
    doc.state = DocumentState.active.value
    db.commit()
    return {"status": "ingested", "chunks": len(chunk_rows),
            "vectors": len(points), "summary": True}
