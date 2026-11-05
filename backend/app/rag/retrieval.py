"""RAG query pipeline: cache-first, registry-authorized, fence-aware.

Guarantees implemented here:
* Qdrant matches and Redis hits alone are never authorization — every candidate
  is re-checked against PostgreSQL (workspace, lifecycle, tombstones) and the
  fence is re-checked immediately before publication (gate_publish).
* The full supplied source set is registered for the answer, not only the
  citations the model chose to print.
* Buffered responses only (no streaming unvalidated content).
"""
from __future__ import annotations

import re
import time
import uuid

from sqlalchemy.orm import Session

from ..config import Settings
from ..connectors.qdrant_c import QdrantConnector
from ..connectors.redis_c import RedisConnector
from ..fence import current_fence_generation, gate_publish
from ..models import Artifact, ArtifactType, CacheEntry, LifecycleState, Relationship, Tombstone
from ..provenance import register_artifact, register_edge
from .cache import (
    cache_key,
    model_version_label,
    normalize_query,
    store_cache_entry,
    validate_cache_hit,
)
from .embeddings import EmbeddingAdapter
from .llm import LLMAdapter


def _is_tombstoned(db: Session, document_id: uuid.UUID) -> bool:
    return (
        db.query(Tombstone.id).filter(Tombstone.document_id == document_id).first()
        is not None
    )


def answer_query(
    db: Session,
    settings: Settings,
    *,
    workspace_id: int,
    question: str,
    document_ids: list[uuid.UUID] | None = None,
    top_k: int = 5,
    embedding: EmbeddingAdapter,
    llm: LLMAdapter,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
) -> dict:
    started = time.perf_counter()
    query_norm = normalize_query(question)
    model_version = model_version_label(embedding.name, llm.name)
    fence_gen = current_fence_generation(db, workspace_id)
    key = cache_key(workspace_id, query_norm, model_version, fence_gen)

    # ---------------------------------------------------------- 1. exact cache
    raw = redis_c.get_json(key)
    if raw is not None:
        entry = db.query(CacheEntry).filter_by(redis_key=key).one_or_none()
        if entry is not None and validate_cache_hit(db, entry, fence_gen):
            latency = (time.perf_counter() - started) * 1000
            payload = dict(raw)
            payload.update({"cache_hit": True, "cache_type": "exact",
                            "latency_ms": round(latency, 1)})
            return payload
        # stale/blocked entry: clean it up and fall through to retrieval
        redis_c.delete([key])

    # ---------------------------------------------------------- 2. retrieval
    qvec = embedding.embed([question])[0]
    doc_filter = [str(d) for d in document_ids] if document_ids else None
    hits = qdrant.search(qvec, limit=top_k * 3, workspace_id=workspace_id,
                         document_ids=doc_filter)

    # Registry authorization of every candidate (a search hit != authorization)
    authorized: list[dict] = []
    for hit in hits:
        payload = hit.get("payload") or {}
        art_id = payload.get("artifact_id")
        doc_id = payload.get("document_id")
        if not art_id or not doc_id:
            continue
        art = db.get(Artifact, uuid.UUID(art_id))
        if art is None or art.workspace_id != workspace_id:
            continue
        if art.lifecycle_state != LifecycleState.active.value:
            continue
        if _is_tombstoned(db, uuid.UUID(doc_id)):
            continue
        text = (art.meta or {}).get("text", "")
        if not text:
            continue
        authorized.append({
            "score": hit.get("score", 0.0),
            "artifact_id": art_id,
            "chunk_artifact": art,
            "document_id": doc_id,
            "text": text,
        })
        if len(authorized) >= top_k:
            break

    if not authorized:
        latency = (time.perf_counter() - started) * 1000
        return {
            "answer": "INSUFFICIENT_AUTHORIZED_EVIDENCE",
            "answer_note": "No authorized, active sources matched this question.",
            "citations": [],
            "cache_hit": False,
            "cache_type": None,
            "mode": llm.mode,
            "model": llm.name,
            "latency_ms": round(latency, 1),
            "answer_artifact_id": None,
        }

    # ---------------------------------------------------------- 3. generation
    excerpts = [
        {"label": f"S{i + 1}", "source": f"document {a['document_id'][:8]}…",
         "text": a["text"]}
        for i, a in enumerate(authorized)
    ]
    answer_text = llm.answer(question, excerpts)
    cited_labels = sorted(set(re.findall(r"\[S(\d+)\]", answer_text or "")))

    citations = [
        {
            "label": e["label"],
            "chunk_artifact_id": au["artifact_id"],
            "document_id": au["document_id"],
            "score": au["score"],
            "snippet": au["text"][:400],
        }
        for e, au in zip(excerpts, authorized)
    ]
    doc_ids_used = [uuid.UUID(a["document_id"]) for a in authorized]

    # ---------------------------------------------------------- 4. register
    answer_artifact = register_artifact(
        db,
        workspace_id=workspace_id,
        type=ArtifactType.answer,
        document_id=uuid.UUID(authorized[0]["document_id"]),
        meta={
            "question": question,
            "query_norm": query_norm,
            "answer": answer_text,
            "citations": citations,
            "cited_labels": cited_labels,
            "sources": [au["artifact_id"] for au in authorized],
            "model": llm.name,
            "mode": llm.mode,
            "model_version": model_version,
        },
    )
    for au in authorized:
        register_edge(db, parent=au["chunk_artifact"], child=answer_artifact,
                      relationship=Relationship.answers)

    # ---------------------------------------------------------- 5. fence gate
    # Serialized with deletion acceptance: a query that started before a
    # deletion commit cannot publish an answer built on affected sources.
    generation_now = gate_publish(db, workspace_id, doc_ids_used)

    # ---------------------------------------------------------- 6. cache publish
    answer_payload = {
        "answer_artifact_id": str(answer_artifact.id),
        "answer": answer_text,
        "citations": citations,
        "mode": llm.mode,
        "model": llm.name,
        "query": question,
        "generated_at": answer_artifact.created_at.isoformat(),
    }
    store_cache_entry(
        db,
        redis_c=redis_c,
        answer_artifact=answer_artifact,
        workspace_id=workspace_id,
        question=question,
        query_norm=query_norm,
        model_version=model_version,
        fence_generation=generation_now,
        source_artifact_ids=[uuid.UUID(au["artifact_id"]) for au in authorized],
        document_ids=doc_ids_used,
        payload=answer_payload,
    )
    if settings.enable_semantic_cache:
        qdrant.ensure_cache_collection()
        qdrant.upsert_cache_query(
            str(answer_artifact.id), qvec,
            {"workspace_id": workspace_id, "redis_key": key,
             "model_version": model_version, "fence_generation": generation_now},
        )

    db.commit()
    latency = (time.perf_counter() - started) * 1000
    return {
        **answer_payload,
        "cache_hit": False,
        "cache_type": None,
        "latency_ms": round(latency, 1),
    }
