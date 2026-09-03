"""monitoring tables — tasks P7-DB-1, P7-DB-2, P7-DB-3, P7-DB-4.

Tables:
- reassessment_events (trigger -> outcome)
- hedge_changes (before/after ratio, delta, reason)
- monitoring_state (current_hedge, target_hedge, cooldown_until, trigger_history, monitoring_status)

Revision ID: 0017_monitoring_tables
Revises: 0016_workflow_state
Create Date: 2026-09-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_monitoring_tables"
down_revision: str | Sequence[str] | None = "0016_workflow_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "reassessment_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column(
            "trigger_event_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("monitoring_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context", jsonb_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_reassessment_events_cycle_id",
        "reassessment_events",
        ["cycle_id"],
        unique=False,
    )

    op.create_table(
        "hedge_changes",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column(
            "reassessment_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("reassessment_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("before_hedge_ratio", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("after_hedge_ratio", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("delta", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail", jsonb_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_hedge_changes_cycle_id",
        "hedge_changes",
        ["cycle_id"],
        unique=False,
    )

    op.create_table(
        "monitoring_state",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=True),
        sa.Column("current_hedge", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("target_hedge", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_history", jsonb_type, nullable=False, server_default="[]"),
        sa.Column("monitoring_status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("detail", jsonb_type, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_monitoring_state_cycle_id",
        "monitoring_state",
        ["cycle_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_monitoring_state_cycle_id", table_name="monitoring_state")
    op.drop_table("monitoring_state")
    op.drop_index("ix_hedge_changes_cycle_id", table_name="hedge_changes")
    op.drop_table("hedge_changes")
    op.drop_index("ix_reassessment_events_cycle_id", table_name="reassessment_events")
    op.drop_table("reassessment_events")
