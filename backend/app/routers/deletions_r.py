"""Deletion center routes: request creation, listing, detail, retry,
verification, repair candidates, metadata-only report export."""
from __future__ import annotations

import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, get_workspace, require_operator
from ..errors import NotFound, ValidationFailed
from ..deletion import accept_deletion, retry_deletion
from ..models import (
    DeletionRequest,
    DeletionState,
    DeletionStep,
    VerificationCheck,
)
from ..repair import repair_candidates_for_request
from ..schemas import (
    DeletionRequestCreate,
    DeletionRequestDetail,
    DeletionRequestOut,
    DeletionStepOut,
    RepairCandidateOut,
    VerificationCheckOut,
)

router = APIRouter(prefix="/deletion-requests", tags=["deletions"])


def _out(r: DeletionRequest) -> DeletionRequestOut:
    return DeletionRequestOut(
        id=str(r.id), document_id=str(r.document_id), state=r.state,
        fence_epoch=r.fence_epoch, repair_enabled=r.repair_enabled,
        accepted_at=r.accepted_at, started_at=r.started_at,
        finished_at=r.finished_at, failure_reason=r.failure_reason,
        report=r.report,
    )


@router.post("", response_model=DeletionRequestOut, status_code=202)
def create_deletion_request(body: DeletionRequestCreate,
                            db: Session = Depends(get_db),
                            ws=Depends(get_workspace),
                            user=Depends(require_operator)):
    request, _created = accept_deletion(
        db, workspace_id=ws.id, document_id=uuid.UUID(body.document_id),
        idempotency_key=body.idempotency_key,
        requested_by=user.username, repair_enabled=body.repair_enabled,
    )
    return _out(request)


@router.get("", response_model=list[DeletionRequestOut])
def list_deletion_requests(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db), ws=Depends(get_workspace),
    user=Depends(get_current_user),
):
    q = db.query(DeletionRequest).filter_by(workspace_id=ws.id)
    if status:
        q = q.filter(DeletionRequest.state == status)
    rows = (
        q.order_by(DeletionRequest.accepted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_out(r) for r in rows]


def _get_request(db: Session, ws, request_id: uuid.UUID) -> DeletionRequest:
    r = db.get(DeletionRequest, request_id)
    if r is None or r.workspace_id != ws.id:
        raise NotFound("Deletion request not found.")
    return r


@router.get("/{request_id}", response_model=DeletionRequestDetail)
def get_deletion_request(request_id: uuid.UUID, db: Session = Depends(get_db),
                         ws=Depends(get_workspace),
                         user=Depends(get_current_user)):
    r = _get_request(db, ws, request_id)
    steps = (
        db.query(DeletionStep).filter_by(request_id=r.id)
        .order_by(DeletionStep.id).all()
    )
    checks = (
        db.query(VerificationCheck).filter_by(request_id=r.id)
        .order_by(VerificationCheck.id).all()
    )
    return DeletionRequestDetail(
        **_out(r).model_dump(),
        steps=[
            DeletionStepOut(
                step=s.step, status=s.status, attempts=s.attempts,
                error_code=s.error_code, detail=s.detail,
                started_at=s.started_at, finished_at=s.finished_at,
            )
            for s in steps
        ],
        verification=[
            VerificationCheckOut(
                check_type=c.check_type, target_label=c.target_label,
                result=c.result, error_code=c.error_code, scope=c.scope or {},
                started_at=c.started_at, finished_at=c.finished_at,
            )
            for c in checks
        ],
    )


@router.post("/{request_id}/retry", response_model=DeletionRequestOut)
def retry(request_id: uuid.UUID, db: Session = Depends(get_db),
          ws=Depends(get_workspace), user=Depends(require_operator)):
    r = _get_request(db, ws, request_id)
    return _out(retry_deletion(db, r.id))


@router.get("/{request_id}/verification", response_model=list[VerificationCheckOut])
def verification(request_id: uuid.UUID, db: Session = Depends(get_db),
                 ws=Depends(get_workspace), user=Depends(get_current_user)):
    r = _get_request(db, ws, request_id)
    checks = (
        db.query(VerificationCheck).filter_by(request_id=r.id)
        .order_by(VerificationCheck.id).all()
    )
    return [
        VerificationCheckOut(
            check_type=c.check_type, target_label=c.target_label,
            result=c.result, error_code=c.error_code, scope=c.scope or {},
            started_at=c.started_at, finished_at=c.finished_at,
        )
        for c in checks
    ]


@router.get("/{request_id}/repair-candidates",
            response_model=list[RepairCandidateOut])
def repair_candidates(request_id: uuid.UUID, db: Session = Depends(get_db),
                      ws=Depends(get_workspace), user=Depends(get_current_user)):
    return [RepairCandidateOut(**c)
            for c in repair_candidates_for_request(db, request_id)]


@router.get("/{request_id}/report/export")
def export_report(request_id: uuid.UUID, format: str = Query(default="json",
                                                                pattern="^(json|csv)$"),
                  db: Session = Depends(get_db), ws=Depends(get_workspace),
                  user=Depends(get_current_user)):
    """Metadata-only export: no deleted content, no secrets, no raw prompts."""
    r = _get_request(db, ws, request_id)
    steps = db.query(DeletionStep).filter_by(request_id=r.id).all()
    checks = db.query(VerificationCheck).filter_by(request_id=r.id).all()
    if format == "json":
        payload = {
            "deletion_request": {
                "id": str(r.id), "document_id": str(r.document_id),
                "state": r.state, "fence_epoch": r.fence_epoch,
                "accepted_at": r.accepted_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "failure_reason": r.failure_reason, "report": r.report,
            },
            "steps": [
                {"step": s.step, "status": s.status, "attempts": s.attempts,
                 "error_code": s.error_code, "detail": s.detail}
                for s in steps
            ],
            "verification": [
                {"check_type": c.check_type, "target_label": c.target_label,
                 "result": c.result, "error_code": c.error_code,
                 "finished_at": c.finished_at.isoformat() if c.finished_at else None}
                for c in checks
            ],
            "scope_note": "Metadata only. Verification is evidence from "
                          "specified checks at a recorded time.",
        }
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition":
                     f"attachment; filename=deletion-report-{str(r.id)[:8]}.json"},
        )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["check_type", "target_label", "result", "error_code", "finished_at"])
    for c in checks:
        writer.writerow([c.check_type, c.target_label, c.result, c.error_code,
                         c.finished_at.isoformat() if c.finished_at else ""])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=deletion-report-{str(r.id)[:8]}.csv"},
    )
