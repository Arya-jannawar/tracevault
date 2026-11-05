"""Audit routes: filterable, metadata-only event listing."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, get_workspace
from ..models import AuditEvent
from ..schemas import AuditEventOut

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    operation: str | None = Query(default=None,
                                  description="event type prefix, e.g. deletion"),
    target_id: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db), ws=Depends(get_workspace),
    user=Depends(get_current_user),
):
    q = db.query(AuditEvent)
    if operation:
        q = q.filter(AuditEvent.type.ilike(f"{operation}%"))
    if target_id:
        try:
            rid = uuid.UUID(target_id)
            q = q.filter(AuditEvent.deletion_request_id == rid)
        except ValueError:
            pass
    if from_date:
        q = q.filter(AuditEvent.created_at >= from_date)
    if to_date:
        q = q.filter(AuditEvent.created_at <= to_date)
    rows = (
        q.order_by(AuditEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        AuditEventOut(
            id=e.id, type=e.type, actor=e.actor,
            deletion_request_id=str(e.deletion_request_id)
            if e.deletion_request_id else None,
            payload=e.payload or {}, created_at=e.created_at,
        )
        for e in rows
    ]
