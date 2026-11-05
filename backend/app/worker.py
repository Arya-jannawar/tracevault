"""Restartable background worker: ingestion, deletion, repair, evaluation.

Claims jobs from the PostgreSQL queue with leases; retry with exponential
backoff + jitter; expired leases recovered on every poll. Run:
`python -m app.worker` (or the compose worker service).
"""
from __future__ import annotations

import socket
import time
import uuid

from .config import get_settings
from .connectors.qdrant_c import QdrantConnector
from .connectors.redis_c import RedisConnector
from .db import SessionLocal
from .errors import ConnectorUnavailable, TraceVaultError
from .jobs import claim_job, finish_job, retry_with_backoff
from .models import JobType

WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def build_adapters(settings):
    from .rag.embeddings import get_embedding_adapter
    from .rag.llm import get_llm_adapter

    embedding = get_embedding_adapter(settings)
    llm = get_llm_adapter(settings)
    return embedding, llm


def handle_job(job, db, settings, adapters, qdrant, redis_c) -> None:
    embedding, llm = adapters
    payload = job.payload or {}

    if job.type == JobType.ingest:
        from .ingestion import process_ingestion

        process_ingestion(
            db, settings,
            document_id=uuid.UUID(payload["document_id"]),
            embedding=embedding, llm=llm, qdrant=qdrant,
        )
    elif job.type == JobType.delete:
        from .deletion import run_deletion

        run_deletion(
            db, settings,
            request_id=uuid.UUID(payload["request_id"]),
            qdrant=qdrant, redis_c=redis_c,
        )
    elif job.type == JobType.repair:
        from .repair import run_repair

        run_repair(
            db, settings,
            request_id=uuid.UUID(payload["request_id"]),
            embedding=embedding, qdrant=qdrant,
        )
    elif job.type == JobType.evaluate:
        from .evaluation import run_evaluation

        run_evaluation(db, settings, run_id=uuid.UUID(payload["run_id"]),
                       embedding=embedding, qdrant=qdrant, redis_c=redis_c)
    else:
        raise TraceVaultError(f"Unknown job type {job.type}")


def main() -> None:  # pragma: no cover - entrypoint loop
    settings = get_settings()
    adapters = build_adapters(settings)
    qdrant = QdrantConnector(settings)
    redis_c = RedisConnector(settings)
    print(f"[tracevault-worker] started as {WORKER_ID}", flush=True)
    while True:
        db = SessionLocal()
        try:
            job = claim_job(db, WORKER_ID, settings.worker_lease_seconds)
            if job is None:
                time.sleep(settings.worker_poll_seconds)
                continue
            print(f"[tracevault-worker] job {job.type.value} {job.id}", flush=True)
            try:
                handle_job(job, db, settings, adapters, qdrant, redis_c)
                finish_job(db, job)
            except ConnectorUnavailable as exc:
                db.rollback()
                job.last_error = exc.message
                retry_with_backoff(db, job)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                retry_with_backoff(db, job)
                job.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]
                db.commit()
        except KeyboardInterrupt:
            print("[tracevault-worker] shutting down", flush=True)
            db.close()
            return
        finally:
            db.close()


if __name__ == "__main__":
    main()
