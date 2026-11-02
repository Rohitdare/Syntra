"""Persist Analyst source excerpts and deterministic chunk references.

Revision ID: 0003_claim_evidence_refs
Revises: 0002_job_events_type
Create Date: 2026-10-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_claim_evidence_refs"
down_revision: str | None = "0002_job_events_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("evidence_quote", sa.Text(), nullable=True))
    op.add_column(
        "claims",
        sa.Column(
            "evidence_chunk_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("claims", "evidence_chunk_ids")
    op.drop_column("claims", "evidence_quote")
