"""execution_failures table — task P5-DB-3.

Every execution attempt that does *not* produce a fill leaves an audit row: a
pre-flight abort, a rejected broker submit, a leg that never filled. The row
carries enough to reconstruct what was tried and why it stopped, without
inventing a false ``orders`` / ``fills`` record.

Table: execution_failures
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- order_id: BigInteger / Integer, nullable, FK -> orders(id) ON DELETE SET NULL
  (a pre-flight failure has no order yet)
- leg_symbol: String(32), nullable (order-level failure vs a single leg)
- stage: String(32) — PREFLIGHT | SUBMIT | FILL | ...
- reason: Text
- detail: JSONB (nullable) — structured context (quotes, drift, broker payload)
- failed_at: DateTime(timezone=True), server default now()

Indexes: cycle_id, order_id (mirrors the 0012 secondary-index convention).

Revision ID: 0015_execution_failures
Revises: 0014_snapshot_risk_metrics
Create Date: 2026-09-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_execution_failures"
down_revision: str | Sequence[str] | None = "0014_snapshot_risk_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "execution_failures",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column(
            "order_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("leg_symbol", sa.String(length=32), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail", jsonb_type, nullable=True),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_execution_failures_cycle_id",
        "execution_failures",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_failures_order_id",
        "execution_failures",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_execution_failures_order_id", table_name="execution_failures")
    op.drop_index("ix_execution_failures_cycle_id", table_name="execution_failures")
    op.drop_table("execution_failures")
