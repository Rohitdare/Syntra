"""SQLAlchemy 2.0 ORM models for Research Desk.

Follows docs/03-DATABASE-SCHEMA.md Section 12.
PostgreSQL is the system of record.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all ORM models."""


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Project(Base):
    """User research project."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('active', 'deleting')", name="ck_projects_status"),
        default="active",
        nullable=False,
    )
    next_source_tag: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Source(Base):
    """Source material uploaded or linked in a project."""

    __tablename__ = "sources"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tag: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("kind IN ('pdf', 'url', 'text')", name="ck_sources_kind"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claim_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    stage_collected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stage_analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stage_critiqued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "tag", name="uq_sources_project_tag"),
        UniqueConstraint("project_id", "content_hash", name="uq_sources_project_content_hash"),
    )


class SourceText(Base):
    """Raw cleaned text for a source, stored separately from source metadata."""

    __tablename__ = "source_texts"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_offsets: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    chunker_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["sources.project_id", "sources.id"],
            ondelete="CASCADE",
            name="fk_source_texts_source",
        ),
    )


class Claim(Base):
    """Individual assertion extracted from a source."""

    __tablename__ = "claims"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    importance: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("importance >= 1 AND importance <= 5", name="ck_claims_importance"),
        nullable=False,
    )
    page_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["sources.project_id", "sources.id"],
            ondelete="CASCADE",
            name="fk_claims_source",
        ),
        UniqueConstraint(
            "project_id", "source_id", "claim_index", name="uq_claims_project_source_index"
        ),
    )


class Verdict(Base):
    """Critic verdict evaluating relation between two claims."""

    __tablename__ = "verdicts"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_key_a: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_key_b: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id_a: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id_b: Mapped[str] = mapped_column(String(64), nullable=False)
    source_tag_a: Mapped[str] = mapped_column(String(20), nullable=False)
    source_tag_b: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_text_a: Mapped[str] = mapped_column(Text, nullable=False)
    claim_text_b: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "label IN ('supports', 'contradicts', 'nuances', 'unrelated')",
            name="ck_verdicts_label",
        ),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_verdicts_confidence"),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "claim_key_a"],
            ["claims.project_id", "claims.id"],
            ondelete="CASCADE",
            name="fk_verdicts_claim_a",
        ),
        ForeignKeyConstraint(
            ["project_id", "claim_key_b"],
            ["claims.project_id", "claims.id"],
            ondelete="CASCADE",
            name="fk_verdicts_claim_b",
        ),
        Index("ix_verdicts_proj_label_conf", "project_id", "label", "confidence"),
    )


class Brief(Base):
    """Cited research brief answering a question."""

    __tablename__ = "briefs"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    json_data: Mapped[dict[str, Any]] = mapped_column("json", JSON, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Job(Base):
    """Background or interactive execution job."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("stage IN ('collect', 'analyze', 'critique', 'ask')", name="ck_jobs_stage"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')",
            name="ck_jobs_status",
        ),
        default="queued",
        nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_jobs_status_lease", "status", "lease_expires_at"),
        Index(
            "ix_jobs_user_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_jobs_single_flight",
            "project_id",
            "stage",
            text("coalesce(source_id, '')"),
            "input_hash",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )


class JobEvent(Base):
    """Sequential event log emitted during job execution."""

    __tablename__ = "job_events"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    agent: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "type IN ('status', 'step', 'chunk', 'item', 'result', "
            "'error', 'heartbeat', 'stage_end')",
            name="ck_job_events_type",
        ),
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class UsageLedger(Base):
    """Usage accounting and budget ledger per user."""

    __tablename__ = "usage_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("kind IN ('llm', 'embed')", name="ck_usage_kind"),
        nullable=False,
    )
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    texts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_usage_ledger_user_created", "user_id", "created_at"),)


class AppMeta(Base):
    """Pinned metadata and schema version assertions."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
