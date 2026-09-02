"""positions table — task P1-DB-4.

Table: positions
Columns:
- id: Primary Key (BigInteger / Integer)
- snapshot_id: BigInteger / Integer, FK -> portfolio_snapshots(id) ON DELETE CASCADE
- symbol: String(32)
- qty: Numeric(18, 4)
- avg_price: Numeric(18, 4)
- market_value: Numeric(18, 4)
- asset_class: String(32)
- side: String(16)

Revision ID: 0003_positions
Revises: 0002_portfolio_snapshots
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_positions"
down_revision: str | Sequence[str] | None = "0002_portfolio_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("avg_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("positions")
