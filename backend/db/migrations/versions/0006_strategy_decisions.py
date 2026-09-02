"""strategy_decisions table — task P1-DB-7.

Table: strategy_decisions
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- action: String(32)
- selected_hypothesis_id: BigInteger / Integer, FK -> strategy_hypotheses(id) ON DELETE SET NULL (nullable)
- rationale: Text
- alternatives: JSONB (nullable)
- comparison: JSONB (nullable)

Revision ID: 0006_strategy_decisions
Revises: 0005_strategy_hypotheses
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_strategy_decisions"
down_revision: str | Sequence[str] | None = "0005_strategy_hypotheses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "strategy_decisions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "selected_hypothesis_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("strategy_hypotheses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("alternatives", jsonb_type, nullable=True),
        sa.Column("comparison", jsonb_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("strategy_decisions")
