"""strategy_hypotheses table — task P1-DB-6.

Table: strategy_hypotheses
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- strategy_type: String(64)
- verdict: Enum('ACCEPTED', 'REJECTED', 'MODIFIED', 'NO_ACTION')
- legs: JSONB (nullable)
- metrics: JSONB (nullable)
- rejection_reason: Text (nullable)

Revision ID: 0005_strategy_hypotheses
Revises: 0004_agent_runs
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_strategy_hypotheses"
down_revision: str | Sequence[str] | None = "0004_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERDICT_ENUM = sa.Enum(
    "ACCEPTED",
    "REJECTED",
    "MODIFIED",
    "NO_ACTION",
    name="hypothesis_verdict_enum",
    create_constraint=True,
)


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "strategy_hypotheses",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("verdict", VERDICT_ENUM, nullable=False),
        sa.Column("legs", jsonb_type, nullable=True),
        sa.Column("metrics", jsonb_type, nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("strategy_hypotheses")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        VERDICT_ENUM.drop(bind, checkfirst=True)
