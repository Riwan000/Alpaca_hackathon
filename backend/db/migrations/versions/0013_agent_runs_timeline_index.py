"""Composite index agent_runs(cycle_id, started_at) for timeline reads — task P3-DB-5.

The agent-run timeline read (P3-DB-4's ``GET /agent-runs?cycle_id=``) filters by
``cycle_id`` and orders by ``started_at``. Migration ``0012`` already indexes each
column on its own; a single composite index lets that query seek to the cycle and
walk it in ``started_at`` order without a separate sort.

Revision ID: 0013_agent_runs_timeline_index
Revises: 0012_constraints_and_indexes
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_agent_runs_timeline_index"
down_revision: str | Sequence[str] | None = "0012_constraints_and_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_agent_runs_cycle_id_started_at"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "agent_runs",
        ["cycle_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="agent_runs")
