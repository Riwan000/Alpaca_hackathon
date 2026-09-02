"""portfolio_snapshots table — task P1-DB-3.

Table: portfolio_snapshots
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- ts: DateTime(timezone=True)
- total_value: Numeric(18, 4)
- cash: Numeric(18, 4)
- equity: Numeric(18, 4)
- buying_power: Numeric(18, 4)

Revision ID: 0002_portfolio_snapshots
Revises: 0001_baseline
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_portfolio_snapshots"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
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
        ),
        sa.Column("total_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("buying_power", sa.Numeric(precision=18, scale=4), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
