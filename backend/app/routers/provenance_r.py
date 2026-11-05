"""Provenance routes: bounded graph view + dependency table alternative."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, get_workspace
from ..errors import NotFound
from ..models import Artifact, ArtifactType
from ..provenance import direct_dependencies, direct_dependants, graph_for_root
from ..schemas import GraphOut

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.get("", response_model=GraphOut)
def provenance_graph(
    root: str = Query(..., description="artifact id or 'document:<uuid>'"),
    direction: str = Query(default="dependants", pattern="^(dependants|dependencies)$"),
    include_transitive: bool = Query(default=True),
    depth: int = Query(default=6, ge=1, le=12),
    db: Session = Depends(get_db),
    ws=Depends(get_workspace),
    user=Depends(get_current_user),
):
    root_id = root
    if root.startswith("document:"):
        doc_id = uuid.UUID(root.split(":", 1)[1])
        va = (
            db.query(Artifact)
            .filter_by(document_id=doc_id, type=ArtifactType.document_version)
            .first()
        )
        if va is None:
            raise NotFound("No registered version artifact for this document.")
        root_id = str(va.id)
    graph = graph_for_root(
        db, workspace_id=ws.id, root_artifact_id=uuid.UUID(root_id),
        direction=direction, include_transitive=include_transitive,
        max_depth=depth,
    )
    return GraphOut(**graph)


@router.get("/dependencies/{artifact_id}")
def dependency_table(artifact_id: uuid.UUID, db: Session = Depends(get_db),
                     ws=Depends(get_workspace), user=Depends(get_current_user)):
    """Keyboard-accessible alternative to the graph: direct edges as a table."""
    art = db.get(Artifact, artifact_id)
    if art is None or art.workspace_id != ws.id:
        raise NotFound("Artifact not found.")

    def label(aid: uuid.UUID) -> dict:
        a = db.get(Artifact, aid)
        if a is None:
            return {"id": str(aid), "type": "unknown", "state": "unknown"}
        return {"id": str(a.id), "type": a.type.value,
                "state": a.lifecycle_state,
                "document_id": str(a.document_id) if a.document_id else None}

    parents = direct_dependencies(db, [artifact_id])
    children = direct_dependants(db, [artifact_id])
    return {
        "artifact": label(artifact_id),
        "dependencies": [label(a) for a in parents],
        "dependants": [label(a) for a in children],
    }
