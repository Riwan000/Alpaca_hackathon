"""monitoring_events table — task P1-DB-11.

Table: monitoring_events
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- trigger_type: Enum('PORTFOLIO_DELTA', 'VOLATILITY_SPIKE', 'CORRELATION_BREAKDOWN', 'DRAWDOWN_LIMIT', 'TIME_ELAPSED', 'MANUAL')
- observed: JSONB (nullable)
- threshold: Numeric(18, 4) (nullable)
- fired_at: DateTime(timezone=True)

Revision ID: 0010_monitoring_events
Revises: 0009_fills
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_monitoring_events"
down_revision: str | Sequence[str] | None = "0009_fills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGER_TYPE_ENUM = sa.Enum(
    "PORTFOLIO_DELTA",
    "VOLATILITY_SPIKE",
    "CORRELATION_BREAKDOWN",
    "DRAWDOWN_LIMIT",
    "TIME_ELAPSED",
    "MANUAL",
    name="trigger_type_enum",
    create_constraint=True,
)


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "monitoring_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", TRIGGER_TYPE_ENUM, nullable=False),
        sa.Column("observed", jsonb_type, nullable=True),
        sa.Column("threshold", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("monitoring_events")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        TRIGGER_TYPE_ENUM.drop(bind, checkfirst=True)
