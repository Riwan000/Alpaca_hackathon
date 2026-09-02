"""risk_checks table — task P1-DB-8.

Table: risk_checks
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- verdict: String(32)
- checks: JSONB (nullable)
- violations: JSONB (nullable)
- warnings: JSONB (nullable)
- modifications: JSONB (nullable)

Revision ID: 0007_risk_checks
Revises: 0006_strategy_decisions
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_risk_checks"
down_revision: str | Sequence[str] | None = "0006_strategy_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "risk_checks",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("checks", jsonb_type, nullable=True),
        sa.Column("violations", jsonb_type, nullable=True),
        sa.Column("warnings", jsonb_type, nullable=True),
        sa.Column("modifications", jsonb_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("risk_checks")
