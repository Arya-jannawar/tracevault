"""Behavior tests with deterministic adapters: ingestion idempotency, RAG cache,
deletion protocol, repair semantics, verification, outage handling.

NOTE: these run on SQLite with in-memory connector fakes (labeled TEST
ADAPTERS). Real-service coverage lives in the `integration` marker tests."""
from __future__ import annotations

import uuid

import pytest

from app.deletion import accept_deletion, run_deletion
from app.errors import PublicationBlocked
from app.ingestion import create_document, process_ingestion
from app.models import (
    Artifact,
    ArtifactType,
    CacheEntry,
    DeletionState,
    LifecycleState,
    Summary,
    Tombstone,
)
from app.rag.cache import cache_key, normalize_query
from app.rag.retrieval import answer_query
from app.seed import CORPUS, _seed_summary_ab, seed_demo_workspace, tag_pipeline_artifacts


def _ingest_all(db, settings, workspace, adapters, fake_qdrant):
    emb, llm = adapters
    docs = {}
    for key, spec in CORPUS.items():
        doc = create_document(db, workspace_id=workspace.id, title=spec["title"],
                              content=spec["content"], source_type="txt")
        docs[key] = doc
        process_ingestion(db, settings, document_id=doc.id, embedding=emb,
                          llm=llm, qdrant=fake_qdrant)
    va = db.query(Artifact).filter_by(
        document_id=docs["docA"].id, type=ArtifactType.document_version).one()
    va.meta = {**(va.meta or {}), "gold_key": "docA"}
    tag_pipeline_artifacts(db, workspace.id)
    return docs


def test_ingestion_creates_registry_records(db, settings, workspace, adapters,
                                            fake_qdrant):
    emb, llm = adapters
    doc = create_document(db, workspace_id=workspace.id, title="A",
                          content=CORPUS["docA"]["content"])
    result = process_ingestion(db, settings, document_id=doc.id, embedding=emb,
                               llm=llm, qdrant=fake_qdrant)
    assert result["status"] == "ingested"
    chunks = db.query(Artifact).filter_by(document_id=doc.id,
                                          type=ArtifactType.chunk).all()
    assert len(chunks) >= 2
    assert len(fake_qdrant.points) == len(chunks)
    assert db.query(Summary).count() == 1


def test_ingestion_retry_is_idempotent(db, settings, workspace, adapters,
                                       fake_qdrant):
    emb, llm = adapters
    doc = create_document(db, workspace_id=workspace.id, title="B",
                          content=CORPUS["docB"]["content"])
    r1 = process_ingestion(db, settings, document_id=doc.id, embedding=emb,
                           llm=llm, qdrant=fake_qdrant)
    r2 = process_ingestion(db, settings, document_id=doc.id, embedding=emb,
                           llm=llm, qdrant=fake_qdrant)
    assert r1["status"] == "ingested"
    assert r2["status"] == "already_ingested"
    assert db.query(Artifact).filter_by(document_id=doc.id,
                                        type=ArtifactType.chunk).count() == r1["chunks"]


def test_cited_query_then_exact_cache_hit(db, settings, workspace, adapters,
                                          fake_qdrant, fake_redis):
    emb, llm = adapters
    _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    q = "What is the Nightingale phase 2 budget?"
    r1 = answer_query(db, settings, workspace_id=workspace.id, question=q,
                      embedding=emb, llm=llm, qdrant=fake_qdrant,
                      redis_c=fake_redis)
    assert r1["cache_hit"] is False
    assert r1["citations"], "answer must carry citations"
    r2 = answer_query(db, settings, workspace_id=workspace.id, question=q,
                      embedding=emb, llm=llm, qdrant=fake_qdrant,
                      redis_c=fake_redis)
    assert r2["cache_hit"] is True
    assert r2["cache_type"] == "exact"


def test_single_source_deletion_blocks_all_paths(db, settings, workspace,
                                                 adapters, fake_qdrant,
                                                 fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    q = "What is the Nightingale phase 2 budget?"
    answer_query(db, settings, workspace_id=workspace.id, question=q,
                 embedding=emb, llm=llm, qdrant=fake_qdrant, redis_c=fake_redis)
    assert len(fake_redis.store) >= 1  # cached answer registered

    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-unit-1")
    result = run_deletion(db, settings, request_id=request.id,
                          qdrant=fake_qdrant, redis_c=redis_for(fake_redis))
    db.refresh(request)
    assert request.state == DeletionState.completed.value
    # vectors removed (full points)
    chunk_ids = [str(a.id) for a in db.query(Artifact).filter_by(
        document_id=docs["docA"].id, type=ArtifactType.chunk).all()]
    assert all(cid not in fake_qdrant.points for cid in chunk_ids)
    # cache keys gone
    assert len(fake_redis.store) == 0
    # registry content redacted
    doc = docs["docA"]
    db.refresh(doc)
    assert doc.state == "deleted"
    assert doc.title.startswith("[removed")
    summary_rows = (db.query(Summary, Artifact)
                    .join(Artifact, Artifact.id == Summary.artifact_id)
                    .filter(Artifact.document_id == doc.id).all())
    assert all(s.content.startswith("[removed") for s, _ in summary_rows)


def redis_for(fake_redis):
    return fake_redis


def test_unrelated_document_survives(db, settings, workspace, adapters,
                                     fake_qdrant, fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-unit-2")
    run_deletion(db, settings, request_id=request.id,
                 qdrant=fake_qdrant, redis_c=redis_for(fake_redis))
    c_chunks = db.query(Artifact).filter_by(
        document_id=docs["docC"].id, type=ArtifactType.chunk).all()
    assert all(c.lifecycle_state == LifecycleState.active.value for c in c_chunks)
    assert all(str(c.id) in fake_qdrant.points for c in c_chunks)


def test_multi_source_repair_preserves_independent_claim(db, settings, workspace,
                                                         adapters, fake_qdrant,
                                                         fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    _seed_summary_ab(db, workspace.id)
    db.commit()
    summary_ab = (
        db.query(Artifact)
        .filter_by(workspace_id=workspace.id, type=ArtifactType.summary)
        .all()
    )
    summary_ab = next(a for a in summary_ab
                      if (a.meta or {}).get("gold_key") == "summaryAB")
    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-repair-1",
                                 repair_enabled=True)
    run_deletion(db, settings, request_id=request.id, qdrant=fake_qdrant,
                 redis_c=redis_for(fake_redis))

    from app.repair import run_repair

    repair_settings = settings.model_copy(update={"enable_selective_repair": True})
    out = run_repair(db, repair_settings, request_id=request.id,
                     qdrant=fake_qdrant, embedding=emb)
    assert out["repaired"] == 1
    # replacement: new artifact with only the surviving (docB-supported) content
    replacement = db.get(Artifact, uuid.UUID(out["details"][0]["replacement_artifact_id"]))
    srow = db.get(Summary, replacement.id)
    assert "Nightingale" not in srow.content          # deleted-only fact removed
    assert "Aurora LMS" in srow.content               # independently supported survives
    # old artifact is never reactivated (it may be logically invalidated or
    # already physically removed by the REMOVING step — both are correct)
    db.refresh(summary_ab)
    assert summary_ab.lifecycle_state in (LifecycleState.invalidated.value,
                                          LifecycleState.removed.value)
    assert summary_ab.lifecycle_state != LifecycleState.active.value


def test_repair_without_surviving_support_is_insufficient(db, settings, workspace,
                                                          adapters, fake_qdrant,
                                                          fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    # single-source auto summary of docA: all support dies with docA
    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-repair-2")
    run_deletion(db, settings, request_id=request.id, qdrant=fake_qdrant,
                 redis_c=redis_for(fake_redis))
    from app.repair import run_repair

    repair_settings = settings.model_copy(update={"enable_selective_repair": True})
    out = run_repair(db, repair_settings, request_id=request.id,
                     qdrant=fake_qdrant, embedding=emb)
    assert all(d["status"] == "evidence_insufficient"
               for d in out["details"] if d["summary_artifact_id"])


def test_unknown_provenance_triggers_coverage_warning_and_invalidation(
        db, settings, workspace, adapters, fake_qdrant, fake_redis):
    from app.models import ProvenanceStatus
    from app.provenance import register_artifact

    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    register_artifact(db, workspace_id=workspace.id, type=ArtifactType.answer,
                      provenance_status=ProvenanceStatus.unknown,
                      meta={"answer": "orphan answer"})
    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-unknown-1")
    run_deletion(db, settings, request_id=request.id, qdrant=fake_qdrant,
                 redis_c=redis_for(fake_redis))
    report = request.report or {}
    codes = [w["code"] for w in report.get("coverage_warnings", [])]
    assert "unknown_provenance_artifacts" in codes


def test_qdrant_outage_yields_retry_pending_not_success(db, settings, workspace,
                                                        adapters, fake_qdrant,
                                                        fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    fake_qdrant.available = False  # outage starts after ingestion
    request, _ = accept_deletion(db, workspace_id=workspace.id,
                                 document_id=docs["docA"].id,
                                 idempotency_key="del-outage-1")
    run_deletion(db, settings, request_id=request.id, qdrant=fake_qdrant,
                 redis_c=redis_for(fake_redis))
    db.refresh(request)
    assert request.state == DeletionState.retry_pending.value
    # tombstone + fence remain in force
    assert db.query(Tombstone).filter_by(document_id=docs["docA"].id).count() == 1


def test_publication_blocked_after_fence(db, settings, workspace, adapters,
                                         fake_qdrant, fake_redis):
    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    accept_deletion(db, workspace_id=workspace.id, document_id=docs["docA"].id,
                    idempotency_key="del-fence-1")
    from app.fence import gate_publish

    # a writer that captured state before the fence commits must be rejected
    with pytest.raises(PublicationBlocked):
        gate_publish(db, workspace.id, [docs["docA"].id])


def test_cache_validation_rejects_stale_fence(db, settings, workspace, adapters,
                                              fake_qdrant, fake_redis):
    from app.rag.cache import validate_cache_hit

    emb, llm = adapters
    docs = _ingest_all(db, settings, workspace, adapters, fake_qdrant)
    q = "What is the Nightingale phase 2 budget?"
    answer_query(db, settings, workspace_id=workspace.id, question=q,
                 embedding=emb, llm=llm, qdrant=fake_qdrant, redis_c=fake_redis)
    entry = db.query(CacheEntry).one()
    assert entry.fence_generation == 1
    assert validate_cache_hit(db, entry, fence_generation=99) is False
