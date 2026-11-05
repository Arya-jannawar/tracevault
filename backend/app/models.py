"""SQLAlchemy ORM models — the provenance registry (PostgreSQL is authoritative).

Content-bearing rows (document_versions.content, summaries.content, artifacts.meta
for chunk text) are separated from minimal audit/provenance metadata so content can
be purged while preserving operation records.

Edge direction convention (used everywhere): source/parent -> derived child.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- enums
class ArtifactType(str, enum.Enum):
    document_version = "document_version"
    chunk = "chunk"
    vector = "vector"
    summary = "summary"
    answer = "answer"
    cache_entry = "cache_entry"


class LifecycleState(str, enum.Enum):
    active = "active"
    pending_deletion = "pending_deletion"
    invalidated = "invalidated"
    removed = "removed"


class ProvenanceStatus(str, enum.Enum):
    registered = "registered"
    unknown = "unknown"


class Relationship(str, enum.Enum):
    contains = "contains"          # document_version -> chunk
    has_vector = "has_vector"      # chunk -> vector
    supports = "supports"          # chunk -> summary (claim support evidence)
    summarizes = "summarizes"      # document_version -> summary
    answers = "answers"            # chunk -> answer (retrieved evidence)
    cached_as = "cached_as"        # answer -> cache_entry


class DocumentState(str, enum.Enum):
    active = "active"
    pending_deletion = "pending_deletion"
    deleted = "deleted"


class DeletionState(str, enum.Enum):
    accepted = "ACCEPTED"
    fenced = "FENCED"
    discovering = "DISCOVERING"
    invalidating = "INVALIDATING"
    removing = "REMOVING"
    verifying = "VERIFYING"
    completed = "COMPLETED"
    retry_pending = "RETRY_PENDING"
    incomplete = "INCOMPLETE"
    failed = "FAILED"


class StepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    unknown = "unknown"


class CheckResult(str, enum.Enum):
    passed = "passed"
    failed = "failed"
    unknown = "unknown"
    not_applicable = "not_applicable"


class JobType(str, enum.Enum):
    ingest = "ingest"
    delete = "delete"
    repair = "repair"
    evaluate = "evaluate"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    retry_pending = "retry_pending"


class ClaimStatus(str, enum.Enum):
    pending = "pending"
    supported = "supported"
    removed = "removed"
    uncertain = "uncertain"


# ---------------------------------------------------------------- auth & workspaces
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # viewer | operator
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    fence_generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- documents & content
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=DocumentState.active.value, nullable=False
    )
    # Plain column (no FK) to avoid a circular dependency between the two tables.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    """Content-bearing row for one immutable version of a document."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_doc_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_type: Mapped[str] = mapped_column(String(16), default="txt")  # txt | md | pdf
    filename: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)  # extracted text
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_state: Mapped[str] = mapped_column(String(16), default="active")  # active|removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")


# ---------------------------------------------------------------- artifacts & graph
class Artifact(Base):
    """Any registered derived artifact. Locator points at its external store."""

    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_ws_type", "workspace_id", "type"),
        Index("ix_artifacts_document", "document_id"),
        Index("ix_artifacts_lifecycle", "lifecycle_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    type: Mapped[ArtifactType] = mapped_column(Enum(ArtifactType, name="artifact_type"),
                                               nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(24), default=LifecycleState.active.value, nullable=False
    )
    provenance_status: Mapped[str] = mapped_column(
        String(16), default=ProvenanceStatus.registered.value, nullable=False
    )
    # External storage locator, e.g. {"collection": "...", "point_id": "..."} or
    # {"redis_key": "..."} — resolvable by the matching connector.
    locator: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Type-specific payload: chunk text/offsets, answer question/text/citations,
    # model/mode labels. Content here is lifecycle-managed (invalidated on deletion).
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DependencyEdge(Base):
    """source/parent -> derived/child edge, versioned at registration time."""

    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "parent_artifact_id", "child_artifact_id", "relationship", name="uq_edge"
        ),
        Index("ix_edges_child", "child_artifact_id"),
        Index("ix_edges_parent", "parent_artifact_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False
    )
    child_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False
    )
    source_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    relationship: Mapped[Relationship] = mapped_column(
        Enum(Relationship, name="relationship_type"), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Summary(Base):
    """Content-bearing row for a summary artifact (repair targets this)."""

    __tablename__ = "summaries"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_state: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_summary", "summary_artifact_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    summary_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ClaimStatus.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClaimSupport(Base):
    """Evidence link: claim <- surviving source chunk (+ version + offsets)."""

    __tablename__ = "claim_supports"
    __table_args__ = (
        UniqueConstraint("claim_id", "source_artifact_id", name="uq_claim_support"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    offsets: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CacheEntry(Base):
    """Registry record of a Redis answer cache entry (Redis is never authoritative)."""

    __tablename__ = "cache_entries"

    redis_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    query_norm: Mapped[str] = mapped_column(String(512), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    fence_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    source_artifact_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- deletion machinery
class DeletionRequest(Base):
    __tablename__ = "deletion_requests"
    __table_args__ = (Index("ix_delreq_state", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(24), default=DeletionState.accepted.value)
    fence_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), default="")
    repair_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DeletionStep(Base):
    __tablename__ = "deletion_steps"
    __table_args__ = (UniqueConstraint("request_id", "step", name="uq_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deletion_requests.id"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=StepStatus.pending.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationCheck(Base):
    __tablename__ = "verification_checks"
    __table_args__ = (Index("ix_vchecks_request", "request_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deletion_requests.id"), nullable=False
    )
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    target_label: Mapped[str] = mapped_column(String(256), default="")
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tombstone(Base):
    """Durable 'this document (and every version) is being deleted' marker.

    Created in the acceptance transaction; reads and publications check it.
    """

    __tablename__ = "tombstones"
    __table_args__ = (Index("ix_tombstones_document", "document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fence_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WriteIntent(Base):
    """Durable intent for an external (cross-store) write, staged before publish.

    Lets us reconcile partial writes: anything still pending after a crash is
    cleaned up or settled by background reconciliation — never exposed.
    """

    __tablename__ = "write_intents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    connector: Mapped[str] = mapped_column(String(32), nullable=False)  # qdrant|redis
    state: Mapped[str] = mapped_column(String(16), default="pending")  # pending|published|cancelled
    fence_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------- durable work & audit
class Job(Base):
    """PostgreSQL-backed job queue with leases (safe concurrent claiming)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.queued.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditEvent(Base):
    """Append-only operation record. Metadata only — never document content."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    deletion_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
