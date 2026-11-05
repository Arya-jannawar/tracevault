"""PostgreSQL-backed durable job queue with leases, bounded retries and safe
concurrent claiming (FOR UPDATE SKIP LOCKED on PostgreSQL; plain locking on
SQLite for unit tests)."""
from __future__ import annotations

import random
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job, JobStatus, JobType, utcnow


def schedule_job(
    db: Session,
    job_type: JobType,
    payload: dict,
    *,
    run_after: timedelta | None = None,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        id=uuid.uuid4(),
        type=job_type,
        payload=payload,
        status=JobStatus.queued.value,
        run_after=utcnow() + (run_after or timedelta(0)),
        max_attempts=max_attempts,
    )
    db.add(job)
    db.flush()
    return job


def claim_job(db: Session, worker_id: str, lease_seconds: int) -> Job | None:
    now = utcnow()
    is_pg = db.bind.dialect.name == "postgresql"
    q = (
        db.query(Job)
        .filter(Job.status == JobStatus.queued.value, Job.run_after <= now)
        .order_by(Job.created_at)
        .limit(1)
    )
    if is_pg:
        q = q.with_for_update(skip_locked=True)
    job = q.first()
    if job is None:
        # recover expired leases (crashed worker)
        expired = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.running.value,
                Job.lease_expires_at < now,
            )
            .limit(1)
            .first()
        )
        if expired is not None:
            expired.status = JobStatus.queued.value
            expired.lease_owner = None
            expired.lease_expires_at = None
            db.commit()
        return None
    job.status = JobStatus.running.value
    job.attempts += 1
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    return job


def retry_with_backoff(db: Session, job: Job, *, base_seconds: float = 2.0) -> None:
    """Exponential backoff with jitter, bounded attempts."""
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.failed.value
    else:
        job.status = JobStatus.retry_pending.value
        delay = base_seconds * (2 ** (job.attempts - 1)) + random.uniform(0, 1.0)
        job.run_after = utcnow() + timedelta(seconds=delay)
        job.status = JobStatus.queued.value  # run_after gating handles the delay
    job.lease_owner = None
    job.lease_expires_at = None
    db.commit()


def finish_job(db: Session, job: Job, *, error: str | None = None) -> None:
    job.status = JobStatus.done.value if error is None else JobStatus.failed.value
    job.last_error = error
    job.lease_owner = None
    job.lease_expires_at = None
    db.commit()


def requeue_job(db: Session, job: Job, delay_seconds: float) -> None:
    job.status = JobStatus.queued.value
    job.run_after = utcnow() + timedelta(seconds=delay_seconds)
    job.lease_owner = None
    job.lease_expires_at = None
    db.commit()


def list_jobs(db: Session, limit: int = 50) -> list[Job]:
    return (
        db.query(Job)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )
