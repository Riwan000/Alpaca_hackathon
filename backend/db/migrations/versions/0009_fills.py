"""fills table — task P1-DB-10.

Table: fills
Columns:
- id: Primary Key (BigInteger / Integer)
- order_id: BigInteger / Integer, FK -> orders(id) ON DELETE CASCADE
- leg_symbol: String(32)
- qty: Numeric(18, 4)
- price: Numeric(18, 4)
- filled_at: DateTime(timezone=True)
- slippage: Numeric(18, 4) (nullable)

Revision ID: 0009_fills
Revises: 0008_orders
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_fills"
down_revision: str | Sequence[str] | None = "0008_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fills",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "order_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("leg_symbol", sa.String(length=32), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "filled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("slippage", sa.Numeric(precision=18, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fills")
