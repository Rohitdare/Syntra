"""Initial database schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-27 00:00:00.000000

Follows docs/03-DATABASE-SCHEMA.md Section 12.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("auth_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_auth_subject", "users", ["auth_subject"], unique=True)

    # 2. projects
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            sa.CheckConstraint("status IN ('active', 'deleting')", name="ck_projects_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("next_source_tag", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    # 3. sources
    op.create_table(
        "sources",
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tag", sa.String(length=20), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            sa.CheckConstraint("kind IN ('pdf', 'url', 'text')", name="ck_sources_kind"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("claim_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("topics", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("stage_collected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stage_analyzed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stage_critiqued", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "tag", name="uq_sources_project_tag"),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_sources_project_content_hash"),
    )

    # 4. source_texts
    op.create_table(
        "source_texts",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_offsets", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("chunker_version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["sources.project_id", "sources.id"],
            ondelete="CASCADE",
            name="fk_source_texts_source",
        ),
    )

    # 5. claims
    op.create_table(
        "claims",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "importance",
            sa.Integer(),
            sa.CheckConstraint("importance >= 1 AND importance <= 5", name="ck_claims_importance"),
            nullable=False,
        ),
        sa.Column("page_hint", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["sources.project_id", "sources.id"],
            ondelete="CASCADE",
            name="fk_claims_source",
        ),
        sa.UniqueConstraint(
            "project_id", "source_id", "claim_index", name="uq_claims_project_source_index"
        ),
    )

    # 6. verdicts
    op.create_table(
        "verdicts",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("claim_key_a", sa.String(length=64), nullable=False),
        sa.Column("claim_key_b", sa.String(length=64), nullable=False),
        sa.Column("source_id_a", sa.String(length=64), nullable=False),
        sa.Column("source_id_b", sa.String(length=64), nullable=False),
        sa.Column("source_tag_a", sa.String(length=20), nullable=False),
        sa.Column("source_tag_b", sa.String(length=20), nullable=False),
        sa.Column("claim_text_a", sa.Text(), nullable=False),
        sa.Column("claim_text_b", sa.Text(), nullable=False),
        sa.Column(
            "label",
            sa.String(length=20),
            sa.CheckConstraint(
                "label IN ('supports', 'contradicts', 'nuances', 'unrelated')",
                name="ck_verdicts_label",
            ),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            sa.CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0", name="ck_verdicts_confidence"
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "claim_key_a"],
            ["claims.project_id", "claims.id"],
            ondelete="CASCADE",
            name="fk_verdicts_claim_a",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "claim_key_b"],
            ["claims.project_id", "claims.id"],
            ondelete="CASCADE",
            name="fk_verdicts_claim_b",
        ),
    )
    op.create_index(
        "ix_verdicts_proj_label_conf", "verdicts", ["project_id", "label", "confidence"]
    )

    # 7. briefs
    op.create_table(
        "briefs",
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("json", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # 8. jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.String(length=20),
            sa.CheckConstraint(
                "stage IN ('collect', 'analyze', 'critique', 'ask')", name="ck_jobs_stage"
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')",
                name="ck_jobs_status",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_status_lease", "jobs", ["status", "lease_expires_at"])
    op.create_index(
        "ix_jobs_user_idempotency",
        "jobs",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_jobs_single_flight",
        "jobs",
        ["project_id", "stage", sa.text("coalesce(source_id, '')"), "input_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # 9. job_events
    op.create_table(
        "job_events",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("agent", sa.String(length=20), nullable=False),
        sa.Column(
            "type",
            sa.String(length=20),
            sa.CheckConstraint(
                "type IN ('status', 'step', 'chunk', 'item', 'result', "
                "'error', 'heartbeat', 'stage_end')",
                name="ck_job_events_type",
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
    )

    # 10. usage_ledger
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            sa.CheckConstraint("kind IN ('llm', 'embed')", name="ck_usage_kind"),
            nullable=False,
        ),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("texts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_usage_ledger_user_created", "usage_ledger", ["user_id", "created_at"])

    # 11. app_meta
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_meta")
    op.drop_table("usage_ledger")
    op.drop_table("job_events")
    op.drop_table("jobs")
    op.drop_table("briefs")
    op.drop_table("verdicts")
    op.drop_table("claims")
    op.drop_table("source_texts")
    op.drop_table("sources")
    op.drop_table("projects")
    op.drop_table("users")
