"""Health and system capability routes (honest status, declared boundary)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import check_db_available
from ..models import Job, JobStatus
from ..schemas import CapabilityOut, HealthOut

router = APIRouter(tags=["system"])


@router.get("/health/live", response_model=HealthOut)
def health_live():
    return HealthOut(status="ok", checks={"process": "ok"})


@router.get("/health/ready", response_model=HealthOut)
def health_ready():
    checks = {
        "postgres": check_db_available(),
        "qdrant": _qdrant_health(),
        "redis": _redis_health(),
    }
    status = "ok" if all(checks.values()) else "degraded"
    return HealthOut(status=status, checks=checks)


def _qdrant_health() -> bool:
    try:
        from ..connectors.qdrant_c import QdrantConnector

        return QdrantConnector(get_settings()).health()
    except Exception:  # noqa: BLE001
        return False


def _redis_health() -> bool:
    try:
        from ..connectors.redis_c import RedisConnector

        return RedisConnector(get_settings()).health()
    except Exception:  # noqa: BLE001
        return False


@router.get("/system/capabilities", response_model=CapabilityOut)
def capabilities(db: Session = Depends(lambda: None), request: Request = None):
    settings = get_settings()
    pending_jobs = 0
    try:
        pending_jobs = (
            db.query(Job)
            .filter(Job.status.in_([JobStatus.queued.value, JobStatus.running.value]))
            .count()
        )
    except Exception:  # noqa: BLE001
        pass
    return CapabilityOut(
        system="TraceVault",
        academic_title=(
            "Provenance-Aware Deletion and Selective Summary Repair for "
            "Privacy-Preserving Retrieval-Augmented Generation (RAG) Systems"
        ),
        tagline="Know the source. Control what remains.",
        is_research_prototype=True,
        operating_modes={
            "embedding_mode": settings.embedding_provider,
            "llm_mode": settings.llm_provider,
            "note": "deterministic/test modes are labeled as such and are not "
                    "research-grade results",
        },
        embedding={
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "dim": settings.embedding_dim,
        },
        llm={
            "provider": settings.llm_provider,
            "model": settings.llm_model if settings.llm_provider == "openai-compatible"
            else "extractive-assembler",
        },
        flags={
            "selective_repair": settings.enable_selective_repair,
            "semantic_cache": settings.enable_semantic_cache,
            "pending_jobs": pending_jobs,
        },
        connectors={
            "postgres": check_db_available(),
            "qdrant": _qdrant_health(),
            "redis": _redis_health(),
        },
        boundary=[
            "Guarantees are limited to registered, controlled components and "
            "tested application pathways.",
            "Not covered: unmanaged backups, snapshots, WAL archives, external "
            "provider telemetry, logs, replicas without connectors, previously "
            "disclosed answers, screenshots and unmanaged client copies.",
            "Application-level blocking is distinct from physical storage removal.",
            "Successful verification is evidence from specified checks at a "
            "recorded time, not universal erasure.",
            "This system is a research prototype; no model unlearning, legal "
            "compliance or certified security is claimed.",
        ],
    )
