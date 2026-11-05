"""Evaluation lab routes: scenarios, run creation (job), listing, detail."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, require_operator
from ..errors import NotFound, ValidationFailed
from ..evaluation import SCENARIOS
from ..jobs import schedule_job
from ..models import EvaluationRun, JobType
from ..schemas import EvaluationRunCreate, EvaluationRunOut, ScenarioOut

router = APIRouter(tags=["evaluation"])


@router.get("/evaluation/scenarios", response_model=list[ScenarioOut])
def scenarios(user=Depends(get_current_user)):
    return [
        ScenarioOut(name=name, description=spec["description"])
        for name, spec in SCENARIOS.items()
    ]


@router.post("/evaluation-runs", response_model=EvaluationRunOut, status_code=202)
def create_run(body: EvaluationRunCreate, db: Session = Depends(get_db),
               user=Depends(require_operator)):
    if body.scenario not in SCENARIOS:
        raise ValidationFailed(
            f"Unknown scenario '{body.scenario}'. Available: {list(SCENARIOS)}."
        )
    settings = get_settings()
    run = EvaluationRun(
        scenario=body.scenario, baseline=body.baseline, seed=body.seed,
        status="queued",
        config={"embedding": settings.embedding_provider,
                "llm": settings.llm_provider, "flag_note": "config captured at "
                "completion with runtime details"},
    )
    db.add(run)
    db.flush()
    schedule_job(db, JobType.evaluate, {"run_id": str(run.id)}, max_attempts=2)
    db.commit()
    return _out(run)


def _out(r: EvaluationRun) -> EvaluationRunOut:
    return EvaluationRunOut(
        id=str(r.id), scenario=r.scenario, baseline=r.baseline, seed=r.seed,
        status=r.status, metrics=r.metrics, counts=r.counts,
        config=r.config or {}, error=r.error,
        started_at=r.started_at, finished_at=r.finished_at,
    )


@router.get("/evaluation-runs", response_model=list[EvaluationRunOut])
def list_runs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc())
        .limit(50).all()
    )
    return [_out(r) for r in rows]


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRunOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    r = db.get(EvaluationRun, run_id)
    if r is None:
        raise NotFound("Evaluation run not found.")
    return _out(r)
