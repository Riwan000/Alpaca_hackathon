"""performance table — task P1-DB-12.

Table: performance
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- ts: DateTime(timezone=True), indexed
- portfolio_pnl: Numeric(18, 4)
- hedge_pnl: Numeric(18, 4)
- net_pnl: Numeric(18, 4)
- drawdown: Numeric(18, 4)
- hedge_cost: Numeric(18, 4)
- benchmark_pnl: Numeric(18, 4)

Revision ID: 0011_performance
Revises: 0010_monitoring_events
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_performance"
down_revision: str | Sequence[str] | None = "0010_monitoring_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column("portfolio_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("hedge_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("drawdown", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("hedge_cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("benchmark_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("performance")
