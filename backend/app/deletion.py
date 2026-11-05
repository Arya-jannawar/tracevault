"""Deletion protocol: acceptance (fence) and the orchestrator state machine.

ACCEPTED -> FENCED -> DISCOVERING -> INVALIDATING -> REMOVING -> VERIFYING -> COMPLETED
with RETRY_PENDING / INCOMPLETE / FAILED carrying explicit reasons.

Logical blocking (registry lifecycle) and physical removal (connectors) are
tracked and reported as distinct outcomes. A deletion is COMPLETED only when
every required in-scope removal and verification check passed; unavailable or
unknown is never success.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .config import Settings
from .connectors.qdrant_c import QdrantConnector
from .connectors.redis_c import RedisConnector
from .errors import IdempotencyConflict, NotFound
from .jobs import schedule_job
from .models import (
    Artifact,
    ArtifactType,
    CacheEntry,
    Claim,
    DeletionRequest,
    DeletionState,
    DeletionStep,
    Document,
    DocumentState,
    DocumentVersion,
    JobType,
    LifecycleState,
    StepStatus,
    Summary,
    Tombstone,
    Workspace,
    utcnow,
)
from .provenance import affected_set_for_document

REDACTED = "[removed by deletion request]"


# ------------------------------------------------------------------ acceptance
def accept_deletion(
    db: Session,
    *,
    workspace_id: int,
    document_id: uuid.UUID,
    idempotency_key: str,
    requested_by: str = "",
    repair_enabled: bool = False,
) -> tuple[DeletionRequest, bool]:
    """Durable acceptance: tombstone + fence + job in ONE transaction.

    Returns (request, created). Reusing a key with a different payload is a
    conflict, not a silent replay. The commit is the acceptance linearization
    point: after it, reads observe the tombstone and publications are fenced.
    """
    existing = db.scalar(
        select(DeletionRequest).where(DeletionRequest.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.document_id != document_id:
            raise IdempotencyConflict(
                "Idempotency key was already used for a different document."
            )
        return existing, False

    doc = db.get(Document, document_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise NotFound("Document not found in this workspace.")
    if doc.state in (DocumentState.pending_deletion.value, DocumentState.deleted.value):
        raise NotFound("Document is already pending deletion or deleted.")

    # serialize with gate_publish on the workspace row
    ws = db.execute(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    ).scalar_one()

    request = DeletionRequest(
        workspace_id=workspace_id,
        document_id=document_id,
        idempotency_key=idempotency_key,
        state=DeletionState.accepted.value,
        fence_epoch=ws.fence_generation + 1,
        requested_by=requested_by[:64],
        repair_enabled=repair_enabled,
        accepted_at=utcnow(),
    )
    db.add(request)
    db.flush()
    db.add(Tombstone(workspace_id=workspace_id, document_id=document_id,
                     fence_epoch=request.fence_epoch))
    ws.fence_generation = request.fence_epoch
    doc.state = DocumentState.pending_deletion.value
    request.state = DeletionState.fenced.value
    record_audit(
        db, type="deletion.accepted", actor=requested_by or "operator",
        deletion_request_id=request.id,
        payload={"document_id": str(document_id), "fence_epoch": request.fence_epoch},
    )
    schedule_job(db, JobType.delete, {"request_id": str(request.id)}, max_attempts=5)
    db.commit()
    return request, True


# ------------------------------------------------------------------ steps
def _step(db: Session, request: DeletionRequest, name: str) -> DeletionStep:
    row = db.scalar(
        select(DeletionStep).where(
            DeletionStep.request_id == request.id, DeletionStep.step == name
        )
    )
    if row is None:
        row = DeletionStep(request_id=request.id, step=name)
        db.add(row)
        db.flush()
    return row


def _begin_step(db: Session, request: DeletionRequest, name: str) -> DeletionStep:
    step = _step(db, request, name)
    step.status = StepStatus.running.value
    step.started_at = step.started_at or utcnow()
    step.attempts += 1
    request.state = name
    db.commit()
    return step


def _fail_step(db: Session, request: DeletionRequest, step: DeletionStep,
               error_code: str, detail: dict | None = None) -> None:
    step.status = StepStatus.failed.value
    step.error_code = error_code
    step.detail = detail
    step.finished_at = utcnow()
    request.state = DeletionState.retry_pending.value
    request.failure_reason = error_code
    db.commit()


def _pass_step(db: Session, step: DeletionStep, detail: dict | None = None) -> None:
    step.status = StepStatus.passed.value
    step.detail = detail
    step.finished_at = utcnow()
    db.commit()


def _reschedule(db: Session, request: DeletionRequest, delay: float = 10.0) -> None:
    schedule_job(db, JobType.delete, {"request_id": str(request.id)},
                 run_after=timedelta(seconds=delay), max_attempts=5)
    db.commit()


# ------------------------------------------------------------------ orchestrator
def run_deletion(
    db: Session,
    settings: Settings,
    *,
    request_id: uuid.UUID,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
) -> dict:
    request = db.get(DeletionRequest, request_id)
    if request is None:
        raise NotFound("Deletion request not found.")
    if request.state == DeletionState.completed.value:
        return {"status": request.state}

    request.started_at = request.started_at or utcnow()
    db.commit()

    # ---- FENCED
    step = _begin_step(db, request, DeletionState.fenced.value)
    tomb = db.scalar(select(Tombstone.id).where(Tombstone.document_id == request.document_id))
    doc = db.get(Document, request.document_id)
    if tomb is None or doc is None:
        _fail_step(db, request, step, "tombstone_missing")
        return {"status": request.state}
    _pass_step(db, step, {"fence_epoch": request.fence_epoch})

    # ---- DISCOVERING
    step = _begin_step(db, request, DeletionState.discovering.value)
    affected, warnings = affected_set_for_document(db, request.document_id,
                                                   request.workspace_id)
    by_type: dict[str, list[str]] = {}
    for a in affected:
        by_type.setdefault(a.type.value, []).append(str(a.id))
    report = dict(request.report or {})
    report.update({
        "affected_count": len(affected),
        "affected_ids": [str(a.id) for a in affected],
        "affected_by_type": by_type,
        "coverage_warnings": warnings,
        "discovered_at": utcnow().isoformat(),
        "scope_exclusions": [
            "Unmanaged backups, snapshots, WAL archives",
            "External provider telemetry and logs",
            "Previously disclosed answers and unmanaged client copies",
            "Replicas or stores without an integrated connector",
        ],
    })
    request.report = report
    _pass_step(db, step, {"affected": len(affected), "warnings": len(warnings)})

    # ---- INVALIDATING (logical blocking through authoritative lifecycle state)
    step = _begin_step(db, request, DeletionState.invalidating.value)
    for art in affected:
        art.lifecycle_state = LifecycleState.invalidated.value
    db.commit()
    _pass_step(db, step, {"logically_invalidated": len(affected)})

    # ---- REMOVING (physical removal through supported connectors)
    step = _begin_step(db, request, DeletionState.removing.value)
    connector_results: dict[str, dict] = {}

    point_ids = by_type.get("chunk", [])
    try:
        q_out = qdrant.delete_points(point_ids, wait=True)
        connector_results["qdrant"] = q_out.to_dict()
    except Exception as exc:  # noqa: BLE001
        connector_results["qdrant"] = {
            "ok": False, "acknowledged": False,
            "error_code": "qdrant_unavailable",
            "detail": f"{exc.__class__.__name__}",
        }

    # redis: registered cache keys via the reverse index (no key scanning)
    doc_str = str(request.document_id)
    relevant_keys = [
        e.redis_key for e in db.query(CacheEntry).all()
        if doc_str in (e.document_ids or [])
    ]
    try:
        r_out = redis_c.delete(relevant_keys)
        connector_results["redis"] = r_out.to_dict()
    except Exception as exc:  # noqa: BLE001
        connector_results["redis"] = {
            "ok": False, "acknowledged": False,
            "error_code": "redis_unavailable",
            "detail": f"{exc.__class__.__name__}",
        }

    # postgres content purge (content rows redacted; operation records remain)
    purge_postgres_content(db, request)
    db.commit()

    if not all(r.get("ok") for r in connector_results.values()):
        # keep tombstone + fence; unavailable is not success
        step.error_code = "connector_failure"
        step.status = StepStatus.unknown.value
        step.detail = connector_results
        step.finished_at = utcnow()
        request.state = DeletionState.retry_pending.value
        request.failure_reason = "connector_failure"
        db.commit()
        _reschedule(db, request)
        return {"status": request.state, "connectors": connector_results}

    step.status = StepStatus.passed.value
    step.detail = connector_results
    step.finished_at = utcnow()
    db.commit()

    # ---- VERIFYING
    step = _begin_step(db, request, DeletionState.verifying.value)
    from .verification import run_verification

    checks = run_verification(db, request, qdrant=qdrant, redis_c=redis_c)
    failed = [c for c in checks if c.result not in ("passed", "not_applicable")]
    if failed:
        step.status = StepStatus.failed.value
        step.error_code = "verification_failed"
        step.finished_at = utcnow()
        request.state = DeletionState.incomplete.value
        request.failure_reason = "verification_failed"
        db.commit()
        return {"status": request.state, "verification": [c.result for c in checks]}
    _pass_step(db, step, {"checks": len(checks)})

    # ---- COMPLETED
    now = utcnow()
    request.state = DeletionState.completed.value
    request.finished_at = now
    report = dict(request.report or {})
    discovered = report.get("discovered_at")
    report.update({
        "completed_at": now.isoformat(),
        "latency": {
            "acceptance_to_discovery_ms": _ms(request.accepted_at, discovered),
            "acceptance_to_completion_ms": _ms(request.accepted_at, now),
        },
        "outcomes": {
            "application_access_blocked": True,
            "stored_records_removed_through_supported_connectors": True,
            "supported_path_verification_passed": True,
            "coverage_incomplete_or_outside_scope": bool(warnings),
        },
    })
    request.report = report
    record_audit(db, type="deletion.completed", deletion_request_id=request.id,
                 payload={"document_id": str(request.document_id),
                          "affected": report.get("affected_count")})
    db.commit()
    return {"status": request.state, "connectors": connector_results}


def _ms(start, end) -> int:
    if isinstance(end, str):
        try:
            end = utcnow().fromisoformat(end)
        except ValueError:
            return 0
    try:
        return int((end - start).total_seconds() * 1000)
    except Exception:  # noqa: BLE001
        return 0


def purge_postgres_content(db: Session, request: DeletionRequest) -> None:
    """Content purge for the full affected set (edges can make artifacts of
    OTHER primary documents dependants of the deleted source — conservative
    invalidation purges them too). Operation/lineage records survive."""
    doc = db.get(Document, request.document_id)
    report = request.report or {}
    affected_ids: list[uuid.UUID] = []
    for raw in report.get("affected_ids", []):
        try:
            affected_ids.append(uuid.UUID(raw))
        except (ValueError, AttributeError):
            continue

    if doc is not None:
        doc.title = REDACTED
        doc.state = DocumentState.deleted.value
        for v in db.query(DocumentVersion).filter_by(document_id=doc.id).all():
            v.content = REDACTED
            v.filename = REDACTED
            v.content_state = "removed"

    # every affected artifact: strip content-bearing meta, keep lineage metadata
    arts = db.query(Artifact).filter(Artifact.id.in_(affected_ids)).all() \
        if affected_ids else []
    if doc is not None and not affected_ids:
        arts = db.query(Artifact).filter(
            Artifact.document_id == doc.id,
            Artifact.type.in_([ArtifactType.chunk, ArtifactType.summary,
                               ArtifactType.answer, ArtifactType.cache_entry]),
        ).all()
    for art in arts:
        meta = dict(art.meta or {})
        for key in ("text", "answer", "question", "query", "citations", "snippet"):
            if key in meta:
                meta[key] = REDACTED
        meta["redacted"] = True
        art.meta = meta
        if art.lifecycle_state != LifecycleState.active.value or \
                art.type in (ArtifactType.chunk, ArtifactType.answer,
                             ArtifactType.cache_entry):
            art.lifecycle_state = LifecycleState.removed.value

    for srow in (
        db.query(Summary)
        .filter(Summary.artifact_id.in_(affected_ids))
        .all()
        if affected_ids else []
    ):
        srow.content = REDACTED
        srow.content_state = "removed"

    for c in (
        db.query(Claim)
        .filter(Claim.summary_artifact_id.in_(affected_ids))
        .all()
        if affected_ids else []
    ):
        c.text = REDACTED
        c.status = "removed"

    # registry rows for cache entries tied to this document (reverse index)
    doc_str = str(request.document_id)
    for entry in db.query(CacheEntry).all():
        if doc_str in (entry.document_ids or []) or \
                (affected_ids and entry.artifact_id in affected_ids):
            db.delete(entry)


def retry_deletion(db: Session, request_id: uuid.UUID) -> DeletionRequest:
    request = db.get(DeletionRequest, request_id)
    if request is None:
        raise NotFound("Deletion request not found.")
    if request.state == DeletionState.completed.value:
        return request
    request.state = DeletionState.retry_pending.value
    request.failure_reason = None
    schedule_job(db, JobType.delete, {"request_id": str(request.id)}, max_attempts=5)
    record_audit(db, type="deletion.retry_requested", deletion_request_id=request.id,
                 payload={"document_id": str(request.document_id)})
    db.commit()
    return request
