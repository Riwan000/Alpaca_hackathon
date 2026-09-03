"""workflow_state table — task P6-DB-1.

Table: workflow_state
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- current_node: Enum('INITIAL', 'ANALYZING', 'STRATEGY_EVALUATION', 'RISK_CHECK', 'EXECUTION', 'MONITORING', 'COMPLETED', 'FAILED')
- status: Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'HALTED')
- detail: JSONB (nullable)
- created_at: DateTime(timezone=True), server default now()
- updated_at: DateTime(timezone=True), server default now()

Table: workflow_transitions
Columns:
- id: Primary Key (BigInteger / Integer)
- cycle_id: String(64)
- from_node: String(64) (nullable)
- to_node: String(64)
- status: String(32)
- detail: JSONB (nullable)
- transitioned_at: DateTime(timezone=True), server default now()

Revision ID: 0016_workflow_state
Revises: 0015_execution_failures
Create Date: 2026-09-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_workflow_state"
down_revision: str | Sequence[str] | None = "0015_execution_failures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_NODE_ENUM = sa.Enum(
    "INITIAL",
    "ANALYZING",
    "STRATEGY_EVALUATION",
    "RISK_CHECK",
    "EXECUTION",
    "MONITORING",
    "COMPLETED",
    "FAILED",
    name="workflow_node_enum",
    create_constraint=True,
)

WORKFLOW_STATUS_ENUM = sa.Enum(
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "HALTED",
    name="workflow_status_enum",
    create_constraint=True,
)


def upgrade() -> None:
    jsonb_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "workflow_state",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("current_node", WORKFLOW_NODE_ENUM, nullable=False),
        sa.Column("status", WORKFLOW_STATUS_ENUM, nullable=False),
        sa.Column("detail", jsonb_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_workflow_state_cycle_id",
        "workflow_state",
        ["cycle_id"],
        unique=False,
    )

    op.create_table(
        "workflow_transitions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("from_node", sa.String(length=64), nullable=True),
        sa.Column("to_node", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", jsonb_type, nullable=True),
        sa.Column(
            "transitioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_workflow_transitions_cycle_id",
        "workflow_transitions",
        ["cycle_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_transitions_cycle_id", table_name="workflow_transitions")
    op.drop_table("workflow_transitions")
    op.drop_index("ix_workflow_state_cycle_id", table_name="workflow_state")
    op.drop_table("workflow_state")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        WORKFLOW_STATUS_ENUM.drop(bind, checkfirst=True)
        WORKFLOW_NODE_ENUM.drop(bind, checkfirst=True)
