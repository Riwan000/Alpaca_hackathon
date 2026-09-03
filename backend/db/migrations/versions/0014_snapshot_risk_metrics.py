"""Computed risk-metric columns on portfolio_snapshots — task P3-DB-3.

Per ``docs/adr/0001-risk-metrics-storage.md``, portfolio-level risk metrics live
as numeric columns on ``portfolio_snapshots`` (one row per analysis cycle) rather
than in a dedicated table. This migration adds the three the dashboard's
``RiskOverview`` reads: ``volatility``, ``beta``, ``drawdown``.

Nullable: an early cycle may lack the price history to compute them; the write
path fills them once the quant engine can. ``op.batch_alter_table`` keeps the
add/drop portable to the local SQLite scratch DB.

Revision ID: 0014_snapshot_risk_metrics
Revises: 0013_agent_runs_timeline_index
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_snapshot_risk_metrics"
down_revision: str | Sequence[str] | None = "0013_agent_runs_timeline_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_METRIC_COLUMNS = ("volatility", "beta", "drawdown")


def upgrade() -> None:
    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        for name in _METRIC_COLUMNS:
            batch_op.add_column(
                sa.Column(name, sa.Numeric(precision=18, scale=4), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        for name in reversed(_METRIC_COLUMNS):
            batch_op.drop_column(name)
