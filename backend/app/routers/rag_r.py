"""RAG routes: query, summaries, repair lab."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..connectors.qdrant_c import QdrantConnector
from ..connectors.redis_c import RedisConnector
from ..db import get_db
from ..deps import get_current_user, get_workspace, require_operator
from ..errors import AdapterUnavailable, NotFound
from ..models import (
    Artifact,
    ArtifactType,
    Claim,
    Document,
    Job,
    LifecycleState,
    Summary,
)
from ..rag.embeddings import get_embedding_adapter
from ..rag.llm import get_llm_adapter
from ..rag.retrieval import answer_query
from ..schemas import (
    ClaimOut,
    RagQueryRequest,
    RagQueryResponse,
    Citation,
    RepairJobOut,
    SummaryOut,
)


class RepairRequest(BaseModel):
    deletion_request_id: str | None = None

router = APIRouter(tags=["rag"])


def _adapters():
    settings = get_settings()
    return get_embedding_adapter(settings), get_llm_adapter(settings)


@router.post("/rag/query", response_model=RagQueryResponse)
def rag_query(body: RagQueryRequest, db: Session = Depends(get_db),
              ws=Depends(get_workspace), user=Depends(get_current_user)):
    embedding, llm = _adapters()
    settings = get_settings()
    doc_ids = [uuid.UUID(d) for d in body.document_ids] if body.document_ids else None
    result = answer_query(
        db, settings, workspace_id=ws.id, question=body.question,
        document_ids=doc_ids, top_k=body.top_k,
        embedding=embedding, llm=llm,
        qdrant=QdrantConnector(settings), redis_c=RedisConnector(settings),
    )
    return RagQueryResponse(
        answer=result.get("answer", ""),
        answer_note=result.get("answer_note"),
        citations=[Citation(**c) for c in result.get("citations", [])],
        cache_hit=result.get("cache_hit", False),
        cache_type=result.get("cache_type"),
        mode=result.get("mode", llm.mode),
        model=result.get("model", llm.name),
        latency_ms=result.get("latency_ms", 0),
        answer_artifact_id=result.get("answer_artifact_id"),
    )


def _summary_out(db: Session, art: Artifact) -> SummaryOut:
    srow = db.get(Summary, art.id)
    claims = (
        db.query(Claim).filter_by(summary_artifact_id=art.id).order_by(Claim.idx).all()
    )
    active = art.lifecycle_state == LifecycleState.active.value
    return SummaryOut(
        artifact_id=str(art.id), document_id=str(art.document_id),
        summary_version=art.version,
        content=srow.content if (srow and active and
                                 srow.content_state == "active") else None,
        lifecycle_state=art.lifecycle_state,
        claims=[
            ClaimOut(
                id=str(c.id), idx=c.idx,
                text=c.text if active and c.status != "removed" else None,
                status=c.status,
            )
            for c in claims
        ],
    )


@router.post("/summaries", response_model=SummaryOut, status_code=201)
def create_summary(body: dict, db: Session = Depends(get_db),
                   ws=Depends(get_workspace), user=Depends(require_operator)):
    """Generate (or return the existing) registered summary for a document."""
    from ..ingestion import _build_summary_text
    from ..models import DocumentVersion, Relationship
    from ..chunking import split_sentences, token_overlap
    from ..models import ClaimSupport
    from ..provenance import register_artifact, register_edge

    doc = db.get(Document, uuid.UUID(body["document_id"]))
    if doc is None or doc.workspace_id != ws.id:
        raise NotFound("Document not found.")
    existing = (
        db.query(Artifact)
        .filter_by(document_id=doc.id, type=ArtifactType.summary,
                   lifecycle_state=LifecycleState.active.value)
        .first()
    )
    if existing is not None:
        return _summary_out(db, existing)

    settings = get_settings()
    version = db.get(DocumentVersion, doc.current_version_id)
    va = (
        db.query(Artifact)
        .filter_by(document_id=doc.id, type=ArtifactType.document_version)
        .one()
    )
    _, llm = _adapters()
    text = _build_summary_text(settings, llm, version.content)
    art = register_artifact(db, workspace_id=ws.id, type=ArtifactType.summary,
                            document_id=doc.id, document_version_id=version.id,
                            meta={"summary_version": 1, "mode": "on_demand"})
    db.add(Summary(artifact_id=art.id, content=text, summary_version=1))
    register_edge(db, parent=va, child=art, relationship=Relationship.summarizes)
    chunks = (
        db.query(Artifact).filter_by(document_id=doc.id, type=ArtifactType.chunk)
        .all()
    )
    for i, claim in enumerate(split_sentences(text)):
        row = Claim(summary_artifact_id=art.id, idx=i, text=claim["text"],
                    status="pending")
        db.add(row)
        db.flush()
        best, best_score = None, 0.0
        for ch in chunks:
            score = token_overlap(claim["text"], (ch.meta or {}).get("text", ""))
            if score > best_score:
                best, best_score = ch, score
        if best is not None and best_score >= 0.75:
            row.status = "supported"
            db.add(ClaimSupport(claim_id=row.id, source_artifact_id=best.id,
                                document_id=doc.id, source_version=1,
                                offsets={"start": (best.meta or {}).get("start"),
                                         "end": (best.meta or {}).get("end")}))
            register_edge(db, parent=best, child=art,
                          relationship=Relationship.supports)
        else:
            row.status = "uncertain"
    db.commit()
    return _summary_out(db, art)


@router.get("/summaries/{artifact_id}", response_model=SummaryOut)
def get_summary(artifact_id: uuid.UUID, db: Session = Depends(get_db),
                ws=Depends(get_workspace), user=Depends(get_current_user)):
    art = db.get(Artifact, artifact_id)
    if art is None or art.workspace_id != ws.id or art.type != ArtifactType.summary:
        raise NotFound("Summary not found.")
    return _summary_out(db, art)


@router.post("/summaries/{artifact_id}/repair", response_model=RepairJobOut)
def repair_summary(artifact_id: uuid.UUID,
                   body: "RepairRequest | None" = None,
                   db: Session = Depends(get_db), ws=Depends(get_workspace),
                   user=Depends(require_operator)):
    from ..repair import start_repair

    dr_id = body.deletion_request_id if body else None
    result = start_repair(
        db, get_settings(), summary_artifact_id=artifact_id,
        deletion_request_id=uuid.UUID(dr_id) if dr_id else None,
        requested_by=user.username,
    )
    return RepairJobOut(**result)


@router.get("/repair-jobs/{job_id}")
def repair_job(job_id: uuid.UUID, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found.")
    return {"job_id": str(job.id), "status": job.status, "attempts": job.attempts,
            "last_error": job.last_error}
