"""Pydantic request/response schemas — the single API contract shared with the
frontend. Long operations return job/request IDs and truthful pending status."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ------------------------------------------------------------------ auth
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str


# ------------------------------------------------------------------ documents
class DocumentOut(BaseModel):
    id: str
    title: str
    state: str
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    chunk_count: int = 0
    summary_count: int = 0
    answer_count: int = 0
    cache_count: int = 0


class DocumentDetail(DocumentOut):
    versions: list["DocumentVersionOut"] = []
    coverage_notes: list[str] = []


class DocumentVersionOut(BaseModel):
    id: str
    version: int
    source_type: str
    filename: str
    checksum: str
    content_state: str
    created_at: datetime


class ChunkOut(BaseModel):
    artifact_id: str
    index: int
    start: int
    end: int
    text: str | None
    lifecycle_state: str


class DeletionImpact(BaseModel):
    document_id: str
    affected_count: int
    affected_by_type: dict[str, int]
    coverage_warnings: list[dict] = []
    scope_exclusions: list[str] = []


# ------------------------------------------------------------------ RAG
class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    label: str
    chunk_artifact_id: str
    document_id: str
    score: float
    snippet: str


class RagQueryResponse(BaseModel):
    answer: str
    answer_note: str | None = None
    citations: list[Citation]
    cache_hit: bool
    cache_type: Literal["exact", "semantic"] | None = None
    mode: str
    model: str
    latency_ms: float
    answer_artifact_id: str | None = None


class SummaryCreateRequest(BaseModel):
    document_id: str


class SummaryOut(BaseModel):
    artifact_id: str
    document_id: str
    summary_version: int
    content: str | None
    lifecycle_state: str
    claims: list["ClaimOut"] = []


class ClaimOut(BaseModel):
    id: str
    idx: int
    text: str | None
    status: str


# ------------------------------------------------------------------ provenance
class GraphNode(BaseModel):
    id: str
    type: str
    document_id: str | None
    document_version_id: str | None
    version: int
    lifecycle_state: str
    provenance_status: str
    meta: dict = {}


class GraphEdge(BaseModel):
    parent: str
    child: str
    relationship: str
    source_version: int


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ------------------------------------------------------------------ deletion
class DeletionRequestCreate(BaseModel):
    document_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    repair_enabled: bool = False


class DeletionStepOut(BaseModel):
    step: str
    status: str
    attempts: int
    error_code: str | None
    detail: dict | None
    started_at: datetime | None
    finished_at: datetime | None


class DeletionRequestOut(BaseModel):
    id: str
    document_id: str
    state: str
    fence_epoch: int
    repair_enabled: bool
    accepted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    failure_reason: str | None
    report: dict | None


class DeletionRequestDetail(DeletionRequestOut):
    steps: list[DeletionStepOut] = []
    verification: list["VerificationCheckOut"] = []


class VerificationCheckOut(BaseModel):
    check_type: str
    target_label: str
    result: str
    error_code: str | None
    scope: dict = {}
    started_at: datetime | None
    finished_at: datetime | None


class RepairCandidateOut(BaseModel):
    summary_artifact_id: str
    document_id: str
    summary_version: int
    total_claims: int
    surviving_supports: int
    surviving_source_docs: list[str]
    repairable: bool


class RepairJobOut(BaseModel):
    job_id: str
    status: str


# ------------------------------------------------------------------ audit & reports
class AuditEventOut(BaseModel):
    id: int
    type: str
    actor: str
    deletion_request_id: str | None
    payload: dict
    created_at: datetime


# ------------------------------------------------------------------ evaluation
class EvaluationRunCreate(BaseModel):
    scenario: str
    baseline: Literal[
        "vector_only", "broad_conservative",
        "provenance_conservative", "provenance_repair",
    ]
    seed: int = 42


class EvaluationRunOut(BaseModel):
    id: str
    scenario: str
    baseline: str
    seed: int
    status: str
    metrics: dict | None
    counts: dict | None
    config: dict
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ScenarioOut(BaseModel):
    name: str
    description: str


# ------------------------------------------------------------------ system
class CapabilityOut(BaseModel):
    system: str
    academic_title: str
    tagline: str
    is_research_prototype: Literal[True]
    operating_modes: dict
    embedding: dict
    llm: dict
    flags: dict
    connectors: dict
    boundary: list[str]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict


class Page(BaseModel):
    total: int
    page: int
    page_size: int
