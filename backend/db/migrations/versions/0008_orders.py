"""orders table — task P1-DB-9.

Table: orders
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- broker_order_id: String(128), nullable, unique
- class: String(32)
- legs: JSONB (nullable)
- status: Enum('PENDING', 'SUBMITTED', 'FILLED', 'PARTIALLY_FILLED', 'CANCELLED', 'EXPIRED', 'REJECTED')
- submitted_at: DateTime(timezone=True)

Revision ID: 0008_orders
Revises: 0007_risk_checks
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_orders"
down_revision: str | Sequence[str] | None = "0007_risk_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_STATUS_ENUM = sa.Enum(
    "PENDING",
    "SUBMITTED",
    "FILLED",
    "PARTIALLY_FILLED",
    "CANCELLED",
    "EXPIRED",
    "REJECTED",
    name="order_status_enum",
    create_constraint=True,
)


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), unique=True, nullable=True),
        sa.Column("class", sa.String(length=32), nullable=False),
        sa.Column("legs", jsonb_type, nullable=True),
        sa.Column("status", ORDER_STATUS_ENUM, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("orders")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ORDER_STATUS_ENUM.drop(bind, checkfirst=True)
