"""Selective summary repair (experimental, flag-gated).

Conservative invalidation remains the default and the safety baseline. Repair:

* processes summaries that were invalidated by a deletion request;
* keeps only claims whose surviving support links point to ACTIVE authorized
  sources (deleted, unauthorized, stale and unknown-provenance sources are
  excluded);
* strict mode: assembles the replacement summary from COMPLETE supported source
  sentences with exact offsets and citations — never fragments, never invented
  text. Zero surviving sources => evidence-insufficient, artifact stays
  invalidated;
* publishes a NEW artifact version (with fresh source/fence checks) and never
  reactivates the old one;
* keeps repair lineage as metadata (meta.repair_of) — NOT as a content
  dependency edge to the deleted source, which would wrongly taint the
  replacement; deleting history to hide the relationship is also wrong.

Claim texts of invalidated summaries are purged with the deletion, so repair
works from the surviving support links + surviving source content: the strict
baseline does not need the original text.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .config import Settings
from .connectors.qdrant_c import QdrantConnector
from .errors import Forbidden, NotFound
from .fence import gate_publish
from .models import (
    Artifact,
    ArtifactType,
    Claim,
    ClaimStatus,
    ClaimSupport,
    DeletionRequest,
    LifecycleState,
    Relationship,
    Summary,
    Tombstone,
    utcnow,
)
from .provenance import register_artifact, register_edge


def start_repair(
    db: Session, settings: Settings, *, summary_artifact_id: uuid.UUID,
    deletion_request_id: uuid.UUID | None, requested_by: str,
) -> dict:
    if not settings.enable_selective_repair:
        raise Forbidden(
            "Selective summary repair is disabled (ENABLE_SELECTIVE_REPAIR=false)."
        )
    art = db.get(Artifact, summary_artifact_id)
    if art is None or art.type != ArtifactType.summary:
        raise NotFound("Summary artifact not found.")
    from .jobs import schedule_job
    from .models import JobType

    job = schedule_job(db, JobType.repair, {
        "summary_artifact_id": str(summary_artifact_id),
        "deletion_request_id": str(deletion_request_id) if deletion_request_id else None,
    })
    record_audit(db, type="repair.requested", actor=requested_by,
                 payload={"summary_artifact_id": str(summary_artifact_id)})
    db.commit()
    return {"job_id": str(job.id), "status": "queued"}


def repair_candidates_for_request(db: Session, request_id: uuid.UUID) -> list[dict]:
    """Invalidated summaries with at least one surviving active support link."""
    request = db.get(DeletionRequest, request_id)
    if request is None:
        raise NotFound("Deletion request not found.")
    report = request.report or {}
    ids = [uuid.UUID(a) for a in report.get("affected_ids", [])]
    summaries = (
        db.query(Artifact)
        .filter(Artifact.id.in_(ids),
                Artifact.type == ArtifactType.summary,
                Artifact.lifecycle_state.in_([
                    LifecycleState.invalidated.value,
                    LifecycleState.removed.value,
                ]))
        .all()
    )
    out: list[dict] = []
    for s in summaries:
        # Support LINKS survive content purge by design (docs/deletion-protocol.md):
        # repair works from surviving links + surviving source content, not from
        # the purged claim texts of the invalidated summary.
        supports = (
            db.query(ClaimSupport)
            .join(Claim, Claim.id == ClaimSupport.claim_id)
            .filter(Claim.summary_artifact_id == s.id)
            .all()
        )
        surviving: list[ClaimSupport] = []
        for sup in supports:
            src = db.get(Artifact, sup.source_artifact_id)
            if src is None:
                continue
            if src.lifecycle_state != LifecycleState.active.value:
                continue
            if db.scalar(
                select(Tombstone.id).where(Tombstone.document_id == src.document_id)
            ):
                continue
            surviving.append(sup)
        out.append({
            "summary_artifact_id": str(s.id),
            "document_id": str(s.document_id),
            "summary_version": s.version,
            "total_claims": len({x.claim_id for x in supports}),
            "surviving_supports": len(surviving),
            "surviving_source_docs": sorted({str(x.document_id) for x in surviving}),
            "repairable": bool(surviving),
        })
    return out


def run_repair(
    db: Session,
    settings: Settings,
    *,
    request_id: uuid.UUID | None = None,
    summary_artifact_id: uuid.UUID | None = None,
    qdrant: QdrantConnector | None = None,
    embedding=None,
) -> dict:
    """Repair invalidated summaries. Worker entrypoint (flag must be enabled)."""
    if not settings.enable_selective_repair:
        return {"status": "disabled", "repaired": 0}

    targets: list[Artifact] = []
    if summary_artifact_id is not None:
        art = db.get(Artifact, summary_artifact_id)
        if art is not None and art.lifecycle_state in (
            LifecycleState.invalidated.value, LifecycleState.removed.value,
        ):
            targets = [art]
    elif request_id is not None:
        request = db.get(DeletionRequest, request_id)
        if request is None:
            raise NotFound("Deletion request not found.")
        report = request.report or {}
        ids = [uuid.UUID(a) for a in report.get("affected_ids", [])]
        targets = (
            db.query(Artifact)
            .filter(Artifact.id.in_(ids), Artifact.type == ArtifactType.summary,
                    Artifact.lifecycle_state.in_([
                        LifecycleState.invalidated.value,
                        LifecycleState.removed.value,
                    ]))
            .all()
        )
        if settings is None:  # pragma: no cover
            return {"status": "error", "repaired": 0}

    repaired, insufficient = [], []
    for target in targets:
        result = _repair_one(db, target)
        if result.get("status") == "repaired":
            repaired.append(result)
        else:
            insufficient.append(result)
    db.commit()
    return {"status": "done", "repaired": len(repaired),
            "evidence_insufficient": len(insufficient), "details": repaired + insufficient}


def _repair_one(db: Session, target: Artifact) -> dict:
    # surviving supports: active source chunks in non-tombstoned documents.
    # Claim texts may already be purged (deletion REMOVING step) — links are
    # the durable evidence structure; see docs/deletion-protocol.md.
    supports = (
        db.query(ClaimSupport)
        .join(Claim, Claim.id == ClaimSupport.claim_id)
        .filter(Claim.summary_artifact_id == target.id)
        .all()
    )
    surviving: list[tuple[ClaimSupport, Artifact]] = []
    for sup in supports:
        src = db.get(Artifact, sup.source_artifact_id)
        if src is None or src.lifecycle_state != LifecycleState.active.value:
            continue
        if src.document_id and db.scalar(
            select(Tombstone.id).where(Tombstone.document_id == src.document_id)
        ):
            continue
        text = (src.meta or {}).get("text")
        if not text:
            continue
        surviving.append((sup, src))

    if not surviving:
        target.meta = {**(target.meta or {}), "repair":
                       {"status": "evidence_insufficient", "at": utcnow().isoformat()}}
        return {"summary_artifact_id": str(target.id), "status": "evidence_insufficient"}

    # strict assembly: complete source sentences (with offsets) that back claims
    evidence_pieces: dict[str, dict] = {}
    for sup, src in surviving:
        key = str(src.id)
        if key not in evidence_pieces:
            evidence_pieces[key] = {
                "source_artifact_id": key,
                "document_id": str(src.document_id),
                "offsets": {"start": (src.meta or {}).get("start"),
                            "end": (src.meta or {}).get("end")},
                "sentence": (src.meta or {}).get("text", ""),
            }
    evidence = sorted(evidence_pieces.values(),
                      key=lambda e: (e["document_id"], e["offsets"]["start"] or 0))

    content = " ".join(e["sentence"].strip() for e in evidence)
    primary_doc = uuid.UUID(evidence[0]["document_id"])
    surviving_doc_ids = [uuid.UUID(e["document_id"]) for e in evidence]

    # fresh fence/source check before publication
    gate_publish(db, target.workspace_id, surviving_doc_ids)

    new_artifact = register_artifact(
        db,
        workspace_id=target.workspace_id,
        type=ArtifactType.summary,
        document_id=primary_doc,
        version=(target.version or 1) + 1,
        meta={
            "summary_version": (target.version or 1) + 1,
            "mode": "strict_repair",
            "repair_of": str(target.id),
            "repair_lineage_only": True,
            "evidence": [
                {"document_id": e["document_id"], "offsets": e["offsets"],
                 "source_artifact_id": e["source_artifact_id"]}
                for e in evidence
            ],
        },
    )
    db.add(Summary(artifact_id=new_artifact.id, content=content,
                   summary_version=new_artifact.version))
    # provenance: edges from the SURVIVING sources only
    for e in evidence:
        src = db.get(Artifact, uuid.UUID(e["source_artifact_id"]))
        register_edge(db, parent=src, child=new_artifact,
                      relationship=Relationship.supports)
        version_art = (
            db.query(Artifact)
            .filter_by(document_id=uuid.UUID(e["document_id"]),
                       type=ArtifactType.document_version)
            .first()
        )
        if version_art is not None:
            register_edge(db, parent=version_art, child=new_artifact,
                          relationship=Relationship.summarizes)

    # claims for the new summary: each sentence is fully supported by its source
    for i, e in enumerate(evidence):
        claim = Claim(summary_artifact_id=new_artifact.id, idx=i,
                      text=e["sentence"], status=ClaimStatus.supported.value)
        db.add(claim)
        db.flush()
        db.add(ClaimSupport(
            claim_id=claim.id, source_artifact_id=uuid.UUID(e["source_artifact_id"]),
            document_id=uuid.UUID(e["document_id"]),
            source_version=1,
            offsets=e["offsets"],
        ))

    # lineage metadata on the OLD artifact — it stays invalidated forever
    target.meta = {**(target.meta or {}), "repair": {
        "status": "replaced_by", "replacement_artifact_id": str(new_artifact.id),
        "at": utcnow().isoformat()}}
    record_audit(db, type="repair.published",
                 payload={"summary_artifact_id": str(target.id),
                          "replacement_artifact_id": str(new_artifact.id),
                          "evidence_count": len(evidence)})
    return {
        "summary_artifact_id": str(target.id),
        "status": "repaired",
        "replacement_artifact_id": str(new_artifact.id),
        "evidence_count": len(evidence),
        "surviving_documents": [str(d) for d in surviving_doc_ids],
    }
