"""Fence and publication gate.

Deletion acceptance and content publication serialize on the workspace row:
* acceptance takes `SELECT ... FOR UPDATE` on the workspace, inserts the tombstone
  and bumps `fence_generation` in one transaction;
* any writer that wants to make derived content visible must call `gate_publish`,
  which takes the same row lock and re-checks tombstones. A writer that captured
  state before the deletion commit is therefore rejected at commit time (TOCTOU
  protection with a concrete protocol, not an "if deleted" check).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import ContentBlocked, NotFound, PublicationBlocked
from .models import Document, Tombstone, Workspace


def get_or_create_default_workspace(db: Session, name: str = "default") -> Workspace:
    ws = db.scalar(select(Workspace).where(Workspace.name == name))
    if ws is None:
        ws = Workspace(name=name, fence_generation=1)
        db.add(ws)
        db.commit()
    return ws


def get_workspace(db: Session, name: str) -> Workspace:
    ws = db.scalar(select(Workspace).where(Workspace.name == name))
    if ws is None:
        raise NotFound(f"Workspace '{name}' does not exist.")
    return ws


def current_fence_generation(db: Session, workspace_id: int) -> int:
    ws = db.get(Workspace, workspace_id)
    return ws.fence_generation if ws else 1


def is_document_fenced(db: Session, workspace_id: int, document_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Tombstone.id).where(
                Tombstone.workspace_id == workspace_id,
                Tombstone.document_id == document_id,
            )
        )
        is not None
    )


def assert_document_not_fenced(db: Session, workspace_id: int, document_id: uuid.UUID) -> None:
    if is_document_fenced(db, workspace_id, document_id):
        raise ContentBlocked(
            "Document is tombstoned by a deletion request and cannot be served."
        )


def gate_publish(db: Session, workspace_id: int, document_ids: list[uuid.UUID]) -> int:
    """Commit-time publication gate. Returns the current fence generation.

    Serialized with deletion acceptance through the workspace row lock.
    Raises PublicationBlocked if any source document is tombstoned.
    """
    ws = db.execute(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    ).scalar_one()
    doc_ids = list(set(document_ids))
    for doc_id in doc_ids:
        tomb = db.scalar(
            select(Tombstone.id).where(
                Tombstone.workspace_id == workspace_id,
                Tombstone.document_id == doc_id,
            )
        )
        if tomb is not None:
            db.rollback()
            raise PublicationBlocked(
                "A deletion fence committed for a source document before this "
                "content could be published; staged writes are being cleaned up."
            )
    return ws.fence_generation


def mark_document_deleted_state(db: Session, document_id: uuid.UUID) -> None:
    doc = db.get(Document, document_id)
    if doc is not None:
        from .models import DocumentState

        doc.state = DocumentState.deleted.value
