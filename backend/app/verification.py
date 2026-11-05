"""Supported-path verification: deterministic locator/state checks plus query
probes where known-public synthetic facts exist. Results are PASSED / FAILED /
UNKNOWN / NOT_APPLICABLE — recorded per check with scope and safe error codes.

Verification is evidence from specified checks at a recorded time; it is not a
claim of universal erasure."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .connectors.qdrant_c import QdrantConnector
from .connectors.redis_c import RedisConnector
from .models import (
    Artifact,
    ArtifactType,
    CacheEntry,
    CheckResult,
    DeletionRequest,
    LifecycleState,
    VerificationCheck,
    utcnow,
)


def _record(db: Session, request_id, check_type: str, target_label: str,
            result: CheckResult, *, target_artifact_id: uuid.UUID | None = None,
            error_code: str | None = None, scope: dict | None = None) -> VerificationCheck:
    row = VerificationCheck(
        request_id=request_id,
        check_type=check_type,
        target_artifact_id=target_artifact_id,
        target_label=target_label[:256],
        result=result.value,
        error_code=error_code,
        scope=scope or {},
        started_at=utcnow(),
        finished_at=utcnow(),
    )
    db.add(row)
    return row


def _probe_queries_for_document(db: Session, request: DeletionRequest) -> list[dict]:
    """Deleted-fact probes from the synthetic gold dataset when the target
    document is part of it (known-public fixture facts only). Real-content
    verification never creates a new repository of the deleted data."""
    try:
        from .gold import probes_for_document_key

        version_art = (
            db.query(Artifact)
            .filter(Artifact.document_id == request.document_id,
                    Artifact.type == ArtifactType.document_version)
            .first()
        )
        key = (version_art.meta or {}).get("gold_key") if version_art else None
        return probes_for_document_key(key) if key else []
    except Exception:  # noqa: BLE001
        return []


def run_verification(
    db: Session,
    request: DeletionRequest,
    *,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
    embedding=None,
) -> list[VerificationCheck]:
    report = request.report or {}
    affected_ids = [uuid.UUID(a) for a in report.get("affected_ids", [])]
    artifacts = (
        db.query(Artifact).filter(Artifact.id.in_(affected_ids)).all()
        if affected_ids
        else []
    )
    checks: list[VerificationCheck] = []

    chunks = [a for a in artifacts if a.type == ArtifactType.chunk]
    summaries = [a for a in artifacts if a.type == ArtifactType.summary]
    answers = [a for a in artifacts if a.type == ArtifactType.answer]

    # 1. vector points removed (full points, by explicit ID)
    try:
        found = qdrant.retrieve_points([str(a.id) for a in chunks]) if chunks else []
        found_ids = {p.get("id") for p in found}
        for a in chunks:
            result = CheckResult.failed if str(a.id) in found_ids else CheckResult.passed
            checks.append(_record(
                db, request.id, "vector_point_removed", f"chunk:{str(a.id)[:8]}",
                result, target_artifact_id=a.id,
                error_code=None if result == CheckResult.passed else "point_still_present",
            ))
    except Exception as exc:  # noqa: BLE001
        checks.append(_record(
            db, request.id, "vector_point_removed", "qdrant:all",
            CheckResult.unknown, error_code="qdrant_unavailable",
            scope={"detail": exc.__class__.__name__},
        ))

    # 2. registry state + content redaction
    for a in chunks + summaries + answers:
        ok_state = a.lifecycle_state == LifecycleState.removed.value
        checks.append(_record(
            db, request.id, "registry_state_removed", f"{a.type.value}:{str(a.id)[:8]}",
            CheckResult.passed if ok_state else CheckResult.failed,
            target_artifact_id=a.id,
            error_code=None if ok_state else "state_not_removed",
        ))

    # 3. cache keys gone
    doc_str = str(request.document_id)
    for entry in db.query(CacheEntry).all():
        if doc_str in (entry.document_ids or []):
            try:
                hit = redis_c.get_json(entry.redis_key)
                checks.append(_record(
                    db, request.id, "cache_key_removed",
                    f"redis:{entry.redis_key[:16]}",
                    CheckResult.failed if hit is not None else CheckResult.passed,
                    error_code=None if hit is None else "cache_key_present",
                ))
            except Exception as exc:  # noqa: BLE001
                checks.append(_record(
                    db, request.id, "cache_key_removed", f"redis:{entry.redis_key[:16]}",
                    CheckResult.unknown, error_code="redis_unavailable",
                    scope={"detail": exc.__class__.__name__},
                ))

    # 4. similarity probes with known-public synthetic facts (direct + paraphrase)
    probes = _probe_queries_for_document(db, request)
    if probes and chunks and embedding is not None:
        try:
            residual = 0
            for probe in probes:
                qvec = embedding.embed([probe["query"]])[0]
                hits = qdrant.search(qvec, limit=5,
                                     workspace_id=request.workspace_id)
                if any(h.get("payload", {}).get("document_id") == doc_str
                       for h in hits):
                    residual += 1
            checks.append(_record(
                db, request.id, "similarity_probe", "gold_probes",
                CheckResult.failed if residual else CheckResult.passed,
                error_code=None if not residual else "deleted_facts_still_retrievable",
                scope={"probes": len(probes), "residual_hits": residual,
                       "note": "matches with surviving independent support are "
                               "counted separately in evaluation, not here"},
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(_record(
                db, request.id, "similarity_probe", "gold_probes",
                CheckResult.unknown, error_code="probe_execution_failed",
                scope={"detail": exc.__class__.__name__},
            ))
    else:
        checks.append(_record(
            db, request.id, "similarity_probe", "gold_probes",
            CheckResult.not_applicable,
            scope={"reason": "no_gold_probes_or_no_embedding_adapter"},
        ))

    # 5. unrelated preservation control (must still be accessible)
    control = (
        db.query(Artifact)
        .filter(
            Artifact.workspace_id == request.workspace_id,
            Artifact.type == ArtifactType.chunk,
            Artifact.document_id != request.document_id,
            Artifact.lifecycle_state == LifecycleState.active.value,
        )
        .first()
    )
    if control is not None:
        try:
            found = qdrant.retrieve_points([str(control.id)])
            ok = any(str(p.get("id")) == str(control.id) for p in found)
            checks.append(_record(
                db, request.id, "unrelated_preservation",
                f"chunk:{str(control.id)[:8]}",
                CheckResult.passed if ok else CheckResult.failed,
                target_artifact_id=control.id,
                error_code=None if ok else "unrelated_point_missing",
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(_record(
                db, request.id, "unrelated_preservation", "qdrant:control",
                CheckResult.unknown, error_code="qdrant_unavailable",
                scope={"detail": exc.__class__.__name__},
            ))

    db.commit()
    return checks


def reappearance_check(
    db: Session,
    request: DeletionRequest,
    *,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
) -> None:
    """Delayed re-probe (after retries/restarts): content must not reappear."""
    report = request.report or {}
    affected_ids = [uuid.UUID(a) for a in report.get("affected_ids", [])]
    chunks = (
        db.query(Artifact)
        .filter(Artifact.id.in_(affected_ids), Artifact.type == ArtifactType.chunk)
        .all()
    )
    try:
        found = qdrant.retrieve_points([str(a.id) for a in chunks]) if chunks else []
        result = CheckResult.failed if found else CheckResult.passed
        _record(db, request.id, "delayed_reappearance", "qdrant:recheck", result,
                error_code=None if not found else "points_reappeared")
    except Exception as exc:  # noqa: BLE001
        _record(db, request.id, "delayed_reappearance", "qdrant:recheck",
                CheckResult.unknown, error_code="qdrant_unavailable",
                scope={"detail": exc.__class__.__name__})
    db.commit()
