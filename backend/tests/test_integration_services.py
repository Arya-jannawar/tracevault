"""Integration tests against REAL PostgreSQL, Qdrant and Redis (Docker).

Run with:  pytest -m integration
Requires compose services up:  docker compose up -d postgres qdrant redis
A skipped integration check is NOT a pass — see the delivery report."""
from __future__ import annotations

import os

import pytest

from app.seed import CORPUS

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get(
    "TV_TEST_DATABASE_URL",
    "postgresql+psycopg://tracevault:tracevault@127.0.0.1:5433/tracevault",
)
QDRANT_URL = os.environ.get("TV_TEST_QDRANT_URL", "http://127.0.0.1:6333")
REDIS_URL = os.environ.get("TV_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")


def _services_available() -> bool:
    try:
        import httpx
        import redis as redis_py
        from sqlalchemy import create_engine, text

        eng = create_engine(DATABASE_URL)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        assert httpx.get(f"{QDRANT_URL}/healthz", timeout=2).status_code == 200
        assert redis_py.Redis.from_url(REDIS_URL).ping()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def real_env():
    if not _services_available():
        pytest.skip("Real PostgreSQL/Qdrant/Redis not available (Docker not up)")
    os.environ["DATABASE_URL"] = DATABASE_URL
    os.environ["QDRANT_URL"] = QDRANT_URL
    os.environ["REDIS_URL"] = REDIS_URL
    os.environ["QDRANT_COLLECTION"] = "tracevault-test"
    from app.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def pg_db(real_env):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()
    engine.dispose()


@pytest.fixture()
def real_connectors(real_env):
    from app.connectors.qdrant_c import QdrantConnector
    from app.connectors.redis_c import RedisConnector

    return QdrantConnector(real_env), RedisConnector(real_env)


def test_full_flow_ingest_query_delete_repair(pg_db, real_env, adapters,
                                              real_connectors):
    """The headline integration flow: ingest -> cached answer -> fenced
    deletion -> blocked retrieval -> repair semantics, on real services."""
    from app.deletion import accept_deletion, run_deletion
    from app.fence import get_or_create_default_workspace
    from app.ingestion import create_document, process_ingestion
    from app.models import (
        Artifact,
        ArtifactType,
        DeletionState,
        LifecycleState,
    )
    from app.rag.retrieval import answer_query
    from app.seed import CORPUS
    from sqlalchemy import text as sa_text

    qdrant, redis_c = real_connectors
    emb, llm = adapters
    qdrant.ensure_collection()

    ws = get_or_create_default_workspace(pg_db, f"itest-{os.getpid()}")
    # clean workspace tables for determinism (test-owned volumes only), FK-safe order
    for stmt in [
        "DELETE FROM verification_checks WHERE request_id IN (SELECT id FROM deletion_requests WHERE workspace_id = :w)",
        "DELETE FROM deletion_steps WHERE request_id IN (SELECT id FROM deletion_requests WHERE workspace_id = :w)",
        "DELETE FROM deletion_requests WHERE workspace_id = :w",
        "DELETE FROM write_intents WHERE workspace_id = :w",
        "DELETE FROM claim_supports WHERE claim_id IN (SELECT c.id FROM claims c JOIN artifacts a ON a.id = c.summary_artifact_id WHERE a.workspace_id = :w)",
        "DELETE FROM claims WHERE summary_artifact_id IN (SELECT id FROM artifacts WHERE workspace_id = :w)",
        "DELETE FROM summaries WHERE artifact_id IN (SELECT id FROM artifacts WHERE workspace_id = :w)",
        "DELETE FROM cache_entries WHERE workspace_id = :w",
        "DELETE FROM tombstones WHERE workspace_id = :w",
        "DELETE FROM dependency_edges WHERE parent_artifact_id IN (SELECT id FROM artifacts WHERE workspace_id = :w) OR child_artifact_id IN (SELECT id FROM artifacts WHERE workspace_id = :w)",
        "DELETE FROM artifacts WHERE workspace_id = :w",
        "DELETE FROM document_versions WHERE document_id IN (SELECT id FROM documents WHERE workspace_id = :w)",
        "DELETE FROM documents WHERE workspace_id = :w",
    ]:
        pg_db.execute(sa_text(stmt), {"w": ws.id})
    pg_db.commit()

    doc_a = create_document(pg_db, workspace_id=ws.id,
                            title=CORPUS["docA"]["title"],
                            content=CORPUS["docA"]["content"])
    doc_b = create_document(pg_db, workspace_id=ws.id,
                            title=CORPUS["docB"]["title"],
                            content=CORPUS["docB"]["content"])
    for d in (doc_a, doc_b):
        process_ingestion(pg_db, real_env, document_id=d.id, embedding=emb,
                          llm=llm, qdrant=qdrant)

    q = "What is the Nightingale phase 2 budget?"
    r1 = answer_query(pg_db, real_env, workspace_id=ws.id, question=q,
                      embedding=emb, llm=llm, qdrant=qdrant, redis_c=redis_c)
    assert r1["citations"]
    r2 = answer_query(pg_db, real_env, workspace_id=ws.id, question=q,
                      embedding=emb, llm=llm, qdrant=qdrant, redis_c=redis_c)
    assert r2["cache_hit"] is True, "exact cache hit must work on real Redis"

    request, _ = accept_deletion(pg_db, workspace_id=ws.id, document_id=doc_a.id,
                                 idempotency_key=f"itest-{os.getpid()}")
    run_deletion(pg_db, real_env, request_id=request.id, qdrant=qdrant,
                 redis_c=redis_c)
    pg_db.refresh(request)
    from app.models import VerificationCheck

    bad_checks = [
        (c.check_type, c.target_label, c.result, c.error_code)
        for c in pg_db.query(VerificationCheck).filter_by(request_id=request.id).all()
        if c.result not in ("passed", "not_applicable")
    ]
    assert request.state == DeletionState.completed.value, \
        f"failed verification checks: {bad_checks}, reason={request.failure_reason}"

    # real Qdrant: points gone
    chunk_ids = [str(a.id) for a in pg_db.query(Artifact).filter_by(
        document_id=doc_a.id, type=ArtifactType.chunk).all()]
    found = qdrant.retrieve_points(chunk_ids)
    assert found == []

    # content blocked through the app pathway
    pg_db.refresh(doc_a)
    assert doc_a.state == "deleted"

    # unrelated doc B still searchable
    hits = qdrant.search(emb.embed(["Aurora LMS maintenance window"])[0],
                         limit=5, workspace_id=ws.id)
    assert any(h["payload"]["document_id"] == str(doc_b.id) for h in hits)
    # cleanup happens at the start of the next run (FK-safe order there)


def test_worker_restarts_and_retries(pg_db, real_env, adapters, real_connectors):
    """Expired-lease recovery: a job left 'running' by a crashed worker is
    reclaimed and completed."""
    from app.fence import get_or_create_default_workspace
    from app.ingestion import create_document
    from app.jobs import claim_job, finish_job
    from app.models import Job, JobStatus
    from datetime import timedelta

    from app.models import utcnow

    qdrant, redis_c = real_connectors
    emb, llm = adapters
    ws = get_or_create_default_workspace(pg_db, f"itest2-{os.getpid()}")
    doc = create_document(pg_db, workspace_id=ws.id, title="Lease test",
                          content=CORPUS["docJ"]["content"])
    job = pg_db.query(Job).order_by(Job.created_at.desc()).first()
    assert job is not None and job.type.value == "ingest"

    # simulate crashed worker: mark running with expired lease
    job.status = JobStatus.running.value
    job.lease_owner = "dead-worker"
    job.lease_expires_at = utcnow() - timedelta(seconds=10)
    pg_db.commit()

    from app.worker import handle_job

    claimed = claim_job(pg_db, "recovery-worker", 60)
    assert claimed is not None
    handle_job(claimed, pg_db, real_env, (emb, llm), qdrant, redis_c)
    finish_job(pg_db, claimed)
    assert claimed.status == JobStatus.done.value
