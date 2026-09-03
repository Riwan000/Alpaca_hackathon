"""dashboard performance indexes — task P8-DB-3.

Adds composite indexes to the performance table tuned for fast time series
and snapshot reads on the dashboard.

Revision ID: 0018_dashboard_performance_indexes
Revises: 0017_monitoring_tables
Create Date: 2026-09-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_dashboard_performance_indexes"
down_revision: str | Sequence[str] | None = "0017_monitoring_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_performance_cycle_ts",
        "performance",
        ["cycle_id", "ts"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_performance_cycle_ts", table_name="performance")
