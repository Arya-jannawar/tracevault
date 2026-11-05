"""Provenance registry services: artifact registration, dependency graph,
transitive closure with cycle protection, and affected-set discovery.

Edge direction everywhere: source/parent -> derived/child.

Traversal is a bounded BFS in Python through type-safe ORM queries: portable
across PostgreSQL (runtime) and SQLite (unit tests), cycle-safe by visited-set
plus a hard depth cap, and registration rejects self-edges. At prototype scale
(hundreds of artifacts) this is comfortably fast; a recursive CTE is a noted
optimization in docs/architecture.md.

An absent edge is NOT proof of independence — unknown provenance yields a
coverage warning and conservative blocking under the documented policy.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import (
    Artifact,
    ArtifactType,
    DependencyEdge,
    LifecycleState,
    ProvenanceStatus,
    Relationship,
    utcnow,
)

MAX_TRAVERSAL_DEPTH = 12


# ------------------------------------------------------------------ registration
def register_artifact(
    db: Session,
    *,
    workspace_id: int,
    type: ArtifactType,  # noqa: A002
    document_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    version: int = 1,
    lifecycle_state: LifecycleState = LifecycleState.active,
    provenance_status: ProvenanceStatus = ProvenanceStatus.registered,
    locator: dict | None = None,
    meta: dict | None = None,
    artifact_id: uuid.UUID | None = None,
) -> Artifact:
    artifact = Artifact(
        id=artifact_id or uuid.uuid4(),
        workspace_id=workspace_id,
        type=type,
        document_id=document_id,
        document_version_id=document_version_id,
        version=version,
        lifecycle_state=lifecycle_state.value,
        provenance_status=provenance_status.value,
        locator=locator or {},
        meta=meta or {},
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(artifact)
    db.flush()
    return artifact


def register_edge(
    db: Session,
    *,
    parent: Artifact,
    child: Artifact,
    relationship: Relationship,
    source_version: int = 1,
) -> DependencyEdge | None:
    if parent.id == child.id:
        raise ValueError("Self-edges are rejected (cycle protection).")
    if parent.workspace_id != child.workspace_id:
        raise ValueError("Cross-workspace dependency edges are rejected.")
    existing = (
        db.query(DependencyEdge)
        .filter_by(
            parent_artifact_id=parent.id,
            child_artifact_id=child.id,
            relationship=relationship,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    edge = DependencyEdge(
        parent_artifact_id=parent.id,
        child_artifact_id=child.id,
        source_version=source_version,
        relationship=relationship,
        registered_at=utcnow(),
    )
    db.add(edge)
    db.flush()
    return edge


# ------------------------------------------------------------------ traversal
def _neighbors(db: Session, ids: list[uuid.UUID], direction: str) -> list[uuid.UUID]:
    """One-hop expansion. direction='dependants' follows parent->child."""
    if not ids:
        return []
    q = db.query(DependencyEdge)
    edges = (
        q.filter(DependencyEdge.parent_artifact_id.in_(ids)).all()
        if direction == "dependants"
        else q.filter(DependencyEdge.child_artifact_id.in_(ids)).all()
    )
    return [
        e.child_artifact_id if direction == "dependants" else e.parent_artifact_id
        for e in edges
    ]


def _closure(db: Session, roots: list[uuid.UUID], direction: str,
             max_depth: int = MAX_TRAVERSAL_DEPTH) -> list[uuid.UUID]:
    """Bounded BFS with visited-set cycle protection; excludes the roots."""
    found: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set(roots)
    frontier = [i for i in roots if i not in seen] or list(roots)
    # frontier starts as roots; first expansion looks at their children
    for depth in range(max_depth):
        if not frontier:
            break
        nxt: list[uuid.UUID] = []
        for nid in _neighbors(db, frontier, direction):
            if nid not in seen:
                seen.add(nid)
                found.append(nid)
                nxt.append(nid)
        frontier = nxt
    return found


def transitive_dependants(db: Session, roots: list[uuid.UUID],
                          max_depth: int = MAX_TRAVERSAL_DEPTH) -> list[uuid.UUID]:
    return _closure(db, roots, "dependants", max_depth)


def transitive_dependencies(db: Session, roots: list[uuid.UUID],
                            max_depth: int = MAX_TRAVERSAL_DEPTH) -> list[uuid.UUID]:
    return _closure(db, roots, "dependencies", max_depth)


def direct_dependants(db: Session, artifact_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not artifact_ids:
        return []
    rows = (
        db.query(DependencyEdge.child_artifact_id)
        .filter(DependencyEdge.parent_artifact_id.in_(artifact_ids))
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def direct_dependencies(db: Session, artifact_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not artifact_ids:
        return []
    rows = (
        db.query(DependencyEdge.parent_artifact_id)
        .filter(DependencyEdge.child_artifact_id.in_(artifact_ids))
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


# ------------------------------------------------------------------ affected set
def root_artifacts_for_document(db: Session, document_id: uuid.UUID) -> list[Artifact]:
    """All registered artifacts whose lineage starts at this document (all versions)."""
    return (
        db.query(Artifact)
        .filter(
            Artifact.document_id == document_id,
            Artifact.type.in_([ArtifactType.document_version, ArtifactType.chunk]),
        )
        .all()
    )


def affected_set_for_document(
    db: Session, document_id: uuid.UUID, workspace_id: int | None = None
) -> tuple[list[Artifact], list[dict]]:
    """Returns (affected artifacts incl. transitive dependants, coverage warnings).

    Policy: artifacts with unknown provenance in the same workspace are
    conservatively invalidated too and reported as a coverage limitation
    (an absent edge is not proof of independence).
    """
    if workspace_id is None:
        doc_root = db.query(Artifact).filter_by(document_id=document_id).first()
        workspace_id = doc_root.workspace_id if doc_root else None
    roots = root_artifacts_for_document(db, document_id)
    root_ids = [a.id for a in roots]
    dep_ids = transitive_dependants(db, root_ids)
    affected = (
        db.query(Artifact)
        .filter(
            Artifact.id.in_(root_ids + dep_ids),
            Artifact.lifecycle_state != LifecycleState.removed.value,
        )
        .all()
    )
    warnings: list[dict] = []
    if workspace_id is not None:
        unknown = (
            db.query(Artifact)
            .filter(
                Artifact.workspace_id == workspace_id,
                Artifact.provenance_status == ProvenanceStatus.unknown.value,
                Artifact.lifecycle_state == LifecycleState.active.value,
                Artifact.id.notin_(root_ids + dep_ids),
            )
            .all()
        )
        if unknown:
            warnings.append({
                "code": "unknown_provenance_artifacts",
                "message": (
                    f"{len(unknown)} active artifact(s) in this workspace have "
                    "unknown provenance and will be conservatively invalidated as "
                    "a coverage limitation. An absent edge is not proof of "
                    "independence."
                ),
                "artifact_ids": [str(a.id) for a in unknown],
            })
            affected.extend(unknown)
    if not roots:
        warnings.append({
            "code": "no_registered_artifacts",
            "message": (
                "No registered artifacts found for this document; the deletion "
                "will only tombstone the document record."
            ),
        })
    return affected, warnings


def graph_for_root(
    db: Session,
    *,
    workspace_id: int,
    root_artifact_id: uuid.UUID,
    direction: str = "dependants",
    include_transitive: bool = True,
    max_depth: int = 6,
) -> dict:
    """Bounded graph view for the explorer (bounded by depth, not unlimited)."""
    root = db.get(Artifact, root_artifact_id)
    if root is None or root.workspace_id != workspace_id:
        return {"nodes": [], "edges": []}
    if include_transitive:
        ids = [root.id] + _closure(db, [root.id], direction, max_depth)
    else:
        ids = [root.id] + _neighbors(db, [root.id], direction)
    nodes = db.query(Artifact).filter(Artifact.id.in_(ids)).all()
    if direction == "dependants":
        edge_rows = (
            db.query(DependencyEdge)
            .filter(DependencyEdge.parent_artifact_id.in_(ids))
            .all()
        )
    else:
        edge_rows = (
            db.query(DependencyEdge)
            .filter(DependencyEdge.child_artifact_id.in_(ids))
            .all()
        )
    node_ids = set(ids)
    return {
        "nodes": [_artifact_node(n) for n in nodes],
        "edges": [
            {
                "parent": str(e.parent_artifact_id),
                "child": str(e.child_artifact_id),
                "relationship": e.relationship.value
                if isinstance(e.relationship, Relationship)
                else str(e.relationship),
                "source_version": e.source_version,
            }
            for e in edge_rows
            if e.parent_artifact_id in node_ids and e.child_artifact_id in node_ids
        ],
    }


def _artifact_node(a: Artifact) -> dict:
    return {
        "id": str(a.id),
        "type": a.type.value if isinstance(a.type, ArtifactType) else str(a.type),
        "document_id": str(a.document_id) if a.document_id else None,
        "document_version_id": str(a.document_version_id)
        if a.document_version_id
        else None,
        "version": a.version,
        "lifecycle_state": a.lifecycle_state,
        "provenance_status": a.provenance_status,
        "meta": {
            k: v for k, v in (a.meta or {}).items() if k not in ("text", "answer", "question")
        },
    }
