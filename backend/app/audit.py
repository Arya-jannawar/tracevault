"""Append-only audit events (metadata only — never document content)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import AuditEvent

# Payload keys that must never be written to the audit log.
_FORBIDDEN_KEYS = {"content", "text", "answer", "question", "prompt", "summary",
                   "filename", "title", "snippet", "query"}


def _redact(payload: dict) -> dict:
    clean: dict = {}
    for key, value in payload.items():
        if key.lower() in _FORBIDDEN_KEYS:
            clean[key] = "[redacted]"
        elif isinstance(value, dict):
            clean[key] = _redact(value)
        else:
            clean[key] = value
    return clean


def record_audit(
    db: Session,
    *,
    type: str,  # noqa: A002 - event type name
    actor: str = "system",
    payload: dict | None = None,
    deletion_request_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        type=type,
        actor=actor,
        payload=_redact(payload or {}),
        deletion_request_id=deletion_request_id,
        correlation_id=correlation_id,
    )
    db.add(event)
    return event
