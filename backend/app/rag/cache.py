"""Registered answer cache: Redis payload + authoritative registry record.

Keys incorporate workspace scope, normalized query, model/prompt configuration
and the corpus fence generation. Every hit is validated against the registry
(fence generation, artifact lifecycle, tombstones, source versions) — a Redis
hit alone is never authorization. Source-set reverse index supports direct
invalidation without scanning arbitrary keys.
"""
from __future__ import annotations

import hashlib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.qdrant_c import QdrantConnector
from ..connectors.redis_c import RedisConnector
from ..models import (
    Artifact,
    ArtifactType,
    CacheEntry,
    LifecycleState,
    Relationship,
    Tombstone,
)
from ..provenance import register_artifact, register_edge

CACHE_TTL_SECONDS = 3600


def normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def model_version_label(embedding_name: str, llm_name: str) -> str:
    return f"emb:{embedding_name}|llm:{llm_name}|prompt:v1"


def cache_key(workspace_id: int, query_norm: str, model_version: str,
              fence_generation: int) -> str:
    h = hashlib.sha256(
        f"{workspace_id}|{query_norm}|{model_version}|{fence_generation}".encode()
    ).hexdigest()
    return f"anscache:{h}"


def store_cache_entry(
    db: Session,
    *,
    redis_c: RedisConnector,
    answer_artifact: Artifact,
    workspace_id: int,
    question: str,
    query_norm: str,
    model_version: str,
    fence_generation: int,
    source_artifact_ids: list[uuid.UUID],
    document_ids: list[uuid.UUID],
    payload: dict,
) -> CacheEntry:
    key = cache_key(workspace_id, query_norm, model_version, fence_generation)
    outcome = redis_c.set_json(key, payload, CACHE_TTL_SECONDS)
    if not outcome.ok:
        # Cache write failures never fail the answer; the cache is best-effort.
        payload = payload
    entry = CacheEntry(
        redis_key=key,
        artifact_id=answer_artifact.id,
        workspace_id=workspace_id,
        query_norm=query_norm[:512],
        model_version=model_version[:128],
        fence_generation=fence_generation,
        source_artifact_ids=[str(a) for a in source_artifact_ids],
        document_ids=[str(d) for d in document_ids],
        expires_at=None,
    )
    db.add(entry)
    cache_artifact = register_artifact(
        db,
        workspace_id=workspace_id,
        type=ArtifactType.cache_entry,
        document_id=answer_artifact.document_id,
        locator={"redis_key": key},
        meta={"query_norm": query_norm[:512], "model_version": model_version[:128],
              "fence_generation": fence_generation},
    )
    register_edge(db, parent=answer_artifact, child=cache_artifact,
                  relationship=Relationship.cached_as)
    db.flush()
    return entry


def validate_cache_hit(db: Session, entry: CacheEntry,
                       fence_generation: int) -> bool:
    """Full registry validation of a Redis hit. False => treat as miss + cleanup."""
    if entry.fence_generation != fence_generation:
        return False
    artifact = db.get(Artifact, entry.artifact_id)
    if artifact is None or artifact.lifecycle_state != LifecycleState.active.value:
        return False
    for doc_id in entry.document_ids or []:
        tomb = db.scalar(
            select(Tombstone.id).where(Tombstone.document_id == uuid.UUID(doc_id))
        )
        if tomb is not None:
            return False
    for src_id in entry.source_artifact_ids or []:
        src = db.get(Artifact, uuid.UUID(src_id))
        if src is None or src.lifecycle_state != LifecycleState.active.value:
            return False
    return True


def invalidate_for_documents(db: Session, redis_c: RedisConnector,
                             document_ids: list[uuid.UUID]) -> list[CacheEntry]:
    """Direct reverse-index invalidation (no key scanning)."""
    if not document_ids:
        return []
    doc_strs = [str(d) for d in document_ids]
    entries = db.query(CacheEntry).all()
    hits = [e for e in entries if any(d in (e.document_ids or []) for d in doc_strs)]
    return hits
