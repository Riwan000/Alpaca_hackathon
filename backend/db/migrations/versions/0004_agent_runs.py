"""agent_runs table — task P1-DB-5.

Table: agent_runs
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- agent_name: String(64)
- inputs: JSONB (nullable)
- outputs: JSONB (nullable)
- error: Text (nullable)
- started_at: DateTime(timezone=True)
- finished_at: DateTime(timezone=True, nullable)
- duration_ms: Integer (nullable)

Revision ID: 0004_agent_runs
Revises: 0003_positions
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_agent_runs"
down_revision: str | Sequence[str] | None = "0003_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("inputs", jsonb_type, nullable=True),
        sa.Column("outputs", jsonb_type, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")
