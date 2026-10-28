"""Update job_events check constraint to include all event types from docs/05-API-SPEC.md.

Revision ID: 0002_job_events_type
Revises: 0001_initial
Create Date: 2026-10-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_job_events_type"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_job_events_type", "job_events", type_="check")
    op.create_check_constraint(
        "ck_job_events_type",
        "job_events",
        "type IN ('stage_start', 'status', 'step', 'chunk', 'item', "
        "'doc_read', 'doc_write', 'llm_call', 'warning', 'result', "
        "'error', 'heartbeat', 'stage_end')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_events_type", "job_events", type_="check")
    op.create_check_constraint(
        "ck_job_events_type",
        "job_events",
        "type IN ('status', 'step', 'chunk', 'item', 'result', 'error', 'heartbeat', 'stage_end')",
    )
