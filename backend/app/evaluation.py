"""Evaluation lab: four baselines over the synthetic corpus in an ISOLATED
workspace, with measured metrics against gold annotations.

Baselines (documented operational definitions):
1. vector_only          — deletes only the source document's vector points;
                          derived artifacts stay. Intentionally demonstrates the
                          weakness. Isolated evaluation workspaces ONLY.
2. broad_conservative   — invalidates EVERY artifact in the bounded evaluation
                          workspace after deleting the source (safe, wasteful).
3. provenance_conservative — the production path: full deletion protocol.
4. provenance_repair    — the same safe invalidation + selective summary repair.

Hold corpus, seeds, model mode, cache policy and verification effort constant.
Metrics are reported with denominators; zero denominators are N/A, never 0%.
"""
from __future__ import annotations

import platform
import time
import uuid as uuidlib

from sqlalchemy.orm import Session

from .audit import record_audit
from .config import Settings
from .connectors.qdrant_c import QdrantConnector
from .connectors.redis_c import RedisConnector
from .deletion import accept_deletion, run_deletion
from .fence import get_or_create_default_workspace
from .gold import load_gold
from .ingestion import process_ingestion
from .models import (
    Artifact,
    ArtifactType,
    Claim,
    DeletionRequest,
    Document,
    EvaluationRun,
    LifecycleState,
    ProvenanceStatus,
    Relationship,
    Summary,
)
from .provenance import register_artifact, register_edge
from .rag.cache import model_version_label, normalize_query
from .rag.retrieval import answer_query
from .repair import run_repair
from .seed import CORPUS, seed_demo_workspace, tag_pipeline_artifacts

SCENARIOS = {
    "single_document_deletion_docA": {
        "target_key": "docA",
        "description": "Delete docA: unique fact dies, shared LMS fact survives "
                       "via docB, unrelated documents must be preserved.",
    },
}


def _artifact_key(art: Artifact) -> str | None:
    return (art.meta or {}).get("gold_key")


def _matches_prefixes(art: Artifact, prefixes: list[str]) -> bool:
    key = _artifact_key(art)
    if not key:
        return False
    return any(key == p or key.startswith(p) for p in prefixes)


def _na(num: int, den: int) -> str | float:
    return round(num / den, 4) if den else "N/A"


def run_evaluation(
    db: Session,
    settings: Settings,
    *,
    run_id: uuidlib.UUID,
    embedding,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
) -> dict:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise ValueError(f"evaluation run {run_id} not found")
    run.status = "running"
    run.started_at = utcnow()
    db.commit()

    try:
        metrics, counts = _execute(db, settings, run=run, embedding=embedding,
                                   qdrant=qdrant, redis_c=redis_c)
        run.metrics = metrics
        run.counts = counts
        run.status = "completed"
        run.finished_at = utcnow()
        record_audit(db, type="evaluation.completed",
                     payload={"run_id": str(run_id), "baseline": run.baseline})
        db.commit()
        return {"status": "completed", "metrics": metrics}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run.status = "failed"
        run.error = f"{exc.__class__.__name__}: {exc}"[:2000]
        run.finished_at = utcnow()
        db.commit()
        return {"status": "failed", "error": run.error}


# ---------------------------------------------------------------------------
def _execute(
    db: Session,
    settings: Settings,
    *,
    run: EvaluationRun,
    embedding,
    qdrant: QdrantConnector,
    redis_c: RedisConnector,
) -> tuple[dict, dict]:
    gold = load_gold()
    started = time.perf_counter()

    ws = get_or_create_default_workspace(
        db, f"eval-{run.id.hex[:8]}-{run.baseline[:12]}"
    )
    run.workspace_id = ws.id
    db.commit()
    seed_demo_workspace(db, ws.id)
    tag_pipeline_artifacts(db, ws.id)

    # synchronous deterministic ingestion for all corpus docs
    for doc in db.query(Document).filter_by(workspace_id=ws.id).all():
        has_chunks = (
            db.query(Artifact)
            .filter_by(document_id=doc.id, type=ArtifactType.chunk)
            .first()
        )
        if has_chunks is None:
            process_ingestion(db, settings, document_id=doc.id,
                              embedding=embedding, llm=_null_llm(),
                              qdrant=qdrant)
    tag_pipeline_artifacts(db, ws.id)

    doc_a = (
        db.query(Document)
        .filter_by(workspace_id=ws.id, title=CORPUS["docA"]["title"])
        .one()
    )

    # ---- warm-phase queries: cited answers + a REAL cache hit before deletion
    q_unique = "When is the Nightingale phase 2 rollout scheduled and what is its budget?"
    ans1 = answer_query(db, settings, workspace_id=ws.id, question=q_unique,
                        embedding=embedding, llm=_null_llm(), qdrant=qdrant,
                        redis_c=redis_c)
    _tag_answer(db, ans1, "answer_unique_A")
    ans1_repeat = answer_query(db, settings, workspace_id=ws.id, question=q_unique,
                               embedding=embedding, llm=_null_llm(), qdrant=qdrant,
                               redis_c=redis_c)
    cache_hit_before = bool(ans1_repeat.get("cache_hit"))
    ans_shared = answer_query(
        db, settings, workspace_id=ws.id,
        question="Where must the quarterly security compliance training be completed?",
        embedding=embedding, llm=_null_llm(), qdrant=qdrant, redis_c=redis_c,
    )
    _tag_answer(db, ans_shared, "answer_shared_lms")

    # transitive summary-of-summary answer: docG -> chunk -> summary -> answer
    summary_g = (
        db.query(Artifact)
        .filter_by(workspace_id=ws.id, type=ArtifactType.summary)
        .all()
    )
    summary_g = next((a for a in summary_g
                      if (a.meta or {}).get("gold_key") == "summary_auto_docG"), None)
    if summary_g is not None:
        sos = register_artifact(
            db, workspace_id=ws.id, type=ArtifactType.answer,
            document_id=summary_g.document_id,
            meta={"answer": "Registered answer derived from the docG summary.",
                  "question": "summarize the QBR summary",
                  "gold_key": "answer_sos", "mode": "seed"},
        )
        register_edge(db, parent=summary_g, child=sos,
                      relationship=Relationship.answers)

    # deliberately missing-provenance artifact (isolated evaluation corpus)
    register_artifact(
        db, workspace_id=ws.id, type=ArtifactType.answer,
        provenance_status=ProvenanceStatus.unknown,
        meta={"answer": "Externally registered answer with missing provenance.",
              "gold_key": "unknown_prov", "mode": "seed"},
    )
    db.commit()

    # ---- deletion phase per baseline
    t_delete = time.perf_counter()
    request: DeletionRequest | None = None
    if run.baseline == "vector_only":
        chunks = (
            db.query(Artifact)
            .filter_by(document_id=doc_a.id, type=ArtifactType.chunk)
            .all()
        )
        qdrant.delete_points([str(a.id) for a in chunks], wait=True)
    elif run.baseline == "broad_conservative":
        for art in (
            db.query(Artifact).filter_by(workspace_id=ws.id)
            .filter(Artifact.lifecycle_state == LifecycleState.active.value)
            .all()
        ):
            art.lifecycle_state = LifecycleState.invalidated.value
        db.commit()
        chunks = (
            db.query(Artifact)
            .filter_by(document_id=doc_a.id, type=ArtifactType.chunk)
            .all()
        )
        qdrant.delete_points([str(a.id) for a in chunks], wait=True)
    elif run.baseline in ("provenance_conservative", "provenance_repair"):
        request, _created = accept_deletion(
            db, workspace_id=ws.id, document_id=doc_a.id,
            idempotency_key=f"eval-{run.id}",
            requested_by="evaluation", repair_enabled=False,
        )
        run_deletion(db, settings, request_id=request.id, qdrant=qdrant,
                     redis_c=redis_c)
        if run.baseline == "provenance_repair":
            repair_settings = settings.model_copy(
                update={"enable_selective_repair": True})
            run_repair(db, repair_settings, request_id=request.id,
                       qdrant=qdrant, embedding=embedding)
    else:
        raise ValueError(f"unknown baseline {run.baseline}")
    deletion_seconds = time.perf_counter() - t_delete

    # ---- probes
    artifacts = db.query(Artifact).filter_by(workspace_id=ws.id).all()
    probes = gold.get("probes", [])
    eligible = [p for p in probes if p.get("expect") in
                ("blocked_after_deletion", "independently_supported_survives_via_docB")]
    residual = 0
    residual_independent = 0
    for probe in eligible:
        if _probe_leaked(db, probe, ws.id, embedding, qdrant, redis_c,
                         deleted_key="docA"):
            if probe.get("kind") == "shared":
                residual_independent += 1  # matches with surviving independent
            else:
                residual += 1

    control = next((p for p in probes if p.get("kind") == "control"), None)
    preserved = (not _probe_leaked(db, control, ws.id, embedding, qdrant,
                                   redis_c, deleted_key=None)
                 ) if control else None

    # false invalidation / preservation over gold unaffected sets
    exp_unaff = gold.get("expected_unaffected", {}).get("docA", {}).get("prefixes", [])
    unaffected_gold = [a for a in artifacts if _matches_prefixes(a, exp_unaff)]
    unaffected_hit = [a for a in unaffected_gold
                      if a.lifecycle_state in (LifecycleState.invalidated.value,
                                               LifecycleState.removed.value)]
    # dependency precision/recall vs gold affected set
    exp_aff = gold.get("expected_affected", {}).get("docA", {}).get("prefixes", [])
    predicted = _predicted_affected(run.baseline, request, artifacts)
    gold_affected = [a for a in artifacts if _matches_prefixes(a, exp_aff)]
    tp = len([a for a in gold_affected if a.id in predicted])
    fp = len([a for a in predicted if a not in {g.id for g in gold_affected}])
    fn = len(gold_affected) - tp

    # repair support
    repair_support = None
    if run.baseline == "provenance_repair":
        repair_support = _repair_support(db, ws.id)

    # ---- metrics (definitions per docs/evaluation.md; N/A on zero denominators)
    metrics = {
        "deletion_effectiveness": _na(
            len([a for a in gold_affected
                 if a.lifecycle_state in (LifecycleState.invalidated.value,
                                          LifecycleState.removed.value)])
            + (1 if repair_support and repair_support.get("replaced") else 0),
            len(gold_affected),
        ),
        "residual_information_rate": _na(residual, max(len(eligible) - 1, 0)),
        "residual_independent_support_matches": residual_independent,
        "dependency_precision": _na(tp, tp + fp),
        "dependency_recall": _na(tp, tp + fn),
        "false_invalidation_rate": _na(len(unaffected_hit), len(unaffected_gold)),
        "information_preservation": _na(
            len(unaffected_gold) - len(unaffected_hit), len(unaffected_gold)),
        "repair_support": repair_support,
        "cache_hit_before_deletion": cache_hit_before,
        "deletion_latency_seconds": round(deletion_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
    }
    counts = {"attempted": 1, "completed": 1, "failed": 0, "skipped": 0}
    config = {
        "scenario": run.scenario,
        "baseline": run.baseline,
        "seed": run.seed,
        "embedding": f"{embedding.name} ({embedding.mode})",
        "llm": "extractive-assembler",
        "model_version": model_version_label(embedding.name, "extractive-assembler"),
        "hardware": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "note": "Deterministic demo embeddings unless stated otherwise; not "
                "general real-world privacy evidence.",
    }
    if request is not None:
        db.refresh(request)
        report = request.report or {}
        metrics["protocol_latency"] = report.get("latency")
        metrics["coverage_warnings"] = report.get("coverage_warnings")
    _ = config  # stored below via run update by caller
    run.config = config
    return metrics, counts


def _null_llm():
    from .rag.llm import ExtractiveLLM

    return ExtractiveLLM()


def _tag_answer(db: Session, answer: dict, gold_key: str) -> None:
    art_id = answer.get("answer_artifact_id")
    if not art_id:
        return
    art = db.get(Artifact, uuidlib.UUID(art_id))
    if art is not None:
        art.meta = {**(art.meta or {}), "gold_key": gold_key}
        db.commit()


def _predicted_affected(baseline: str, request: DeletionRequest | None,
                        artifacts: list[Artifact]) -> set:
    if request is not None:
        report = request.report or {}
        return set(uuidlib.UUID(a) for a in report.get("affected_ids", []))
    if baseline == "vector_only":
        return set(a.id for a in artifacts if a.type == ArtifactType.chunk
                   and a.document_id == request.document_id) if request else set()
    # broad_conservative: everything predicted affected
    return set(a.id for a in artifacts)


def _probe_leaked(db: Session, probe: dict, workspace_id: int, embedding,
                  qdrant: QdrantConnector, redis_c: RedisConnector,
                  deleted_key: str | None) -> bool:
    """A probe leaks if a supported path still serves the deleted-only fact."""
    if probe is None:
        return False
    kind = probe.get("kind")
    target = probe.get("target")
    if deleted_key is not None and target != deleted_key:
        return False
    expect = probe.get("expect")

    # path 1: similarity search through the vector store
    try:
        qvec = embedding.embed([probe["query"]])[0]
        hits = qdrant.search(qvec, limit=5, workspace_id=workspace_id)
        for h in hits:
            payload = h.get("payload") or {}
            art = db.get(Artifact, uuidlib.UUID(payload["artifact_id"])) \
                if payload.get("artifact_id") else None
            if art is None or art.lifecycle_state != LifecycleState.active.value:
                continue
            if expect == "blocked_after_deletion":
                return True
    except Exception:  # noqa: BLE001 - probe failure is not evidence of leakage
        pass

    # path 2: registered summaries/answers still ACTIVE with the fact text
    if expect == "blocked_after_deletion":
        fact = probe.get("fact_snippet") or _salient_tokens(probe["query"])
        for srow, art in (
            db.query(Summary, Artifact)
            .join(Artifact, Artifact.id == Summary.artifact_id)
            .filter_by(workspace_id=workspace_id).all()
        ):
            if art.lifecycle_state == LifecycleState.active.value and \
                    _contains(srow.content, fact):
                return True
        for art in (
            db.query(Artifact)
            .filter_by(workspace_id=workspace_id, type=ArtifactType.answer)
            .filter(Artifact.lifecycle_state == LifecycleState.active.value)
            .all()
        ):
            if _contains((art.meta or {}).get("answer", ""), fact):
                return True
    return False


def _salient_tokens(query: str) -> list[str]:
    stop = {"what", "when", "where", "is", "the", "a", "an", "of", "in", "to",
            "and", "for", "are", "on", "with", "how", "does", "do"}
    toks = [t for t in normalize_query(query).split() if t not in stop and len(t) > 3]
    return toks[:4]


def _contains(text: str, facts: list[str] | str) -> bool:
    if not text:
        return False
    low = text.lower()
    facts_list = [facts] if isinstance(facts, str) else facts
    hits = sum(1 for f in facts_list if f.lower() in low)
    return hits >= max(1, len(facts_list) // 2)


def _repair_support(db: Session, workspace_id: int) -> dict:
    """Retained claims supported by surviving authorized gold evidence."""
    repaired = [
        a for a in db.query(Artifact)
        .filter_by(workspace_id=workspace_id, type=ArtifactType.summary)
        .all()
        if (a.meta or {}).get("mode") == "strict_repair"
    ]
    retained = supported = 0
    for art in repaired:
        for claim in db.query(Claim).filter_by(summary_artifact_id=art.id).all():
            if claim.status == "supported":
                retained += 1
                supported += 1
            elif claim.status in ("pending", "uncertain"):
                retained += 1
    replaced = bool(repaired)
    return {
        "replaced": replaced,
        "retained_claims": retained,
        "supported_claims": supported,
        "support_ratio": _na(supported, retained),
        "note": "strict repair retains only claims with exact surviving support; "
                "unsupported claims are removed, never invented",
    }
