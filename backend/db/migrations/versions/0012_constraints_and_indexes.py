"""FK constraints and indexes on cycle_id, ts, snapshot_id, order_id — task P1-DB-13.

Adds secondary indexes across all core schema tables for fast querying by:
- cycle_id (portfolio_snapshots, agent_runs, strategy_hypotheses, strategy_decisions,
            risk_checks, orders, monitoring_events, performance)
- ts / timestamps (portfolio_snapshots.ts, agent_runs.started_at, monitoring_events.fired_at)
- snapshot_id (positions.snapshot_id)
- order_id (fills.order_id)
- foreign keys and lookups (strategy_decisions.selected_hypothesis_id, positions.symbol)

Revision ID: 0012_constraints_and_indexes
Revises: 0011_performance
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_constraints_and_indexes"
down_revision: str | Sequence[str] | None = "0011_performance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. portfolio_snapshots
    op.create_index(
        "ix_portfolio_snapshots_cycle_id",
        "portfolio_snapshots",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_snapshots_ts",
        "portfolio_snapshots",
        ["ts"],
        unique=False,
    )

    # 2. positions
    op.create_index(
        "ix_positions_snapshot_id",
        "positions",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_positions_symbol",
        "positions",
        ["symbol"],
        unique=False,
    )

    # 3. agent_runs
    op.create_index(
        "ix_agent_runs_cycle_id",
        "agent_runs",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_started_at",
        "agent_runs",
        ["started_at"],
        unique=False,
    )

    # 4. strategy_hypotheses
    op.create_index(
        "ix_strategy_hypotheses_cycle_id",
        "strategy_hypotheses",
        ["cycle_id"],
        unique=False,
    )

    # 5. strategy_decisions
    op.create_index(
        "ix_strategy_decisions_cycle_id",
        "strategy_decisions",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_decisions_selected_hypothesis_id",
        "strategy_decisions",
        ["selected_hypothesis_id"],
        unique=False,
    )

    # 6. risk_checks
    op.create_index(
        "ix_risk_checks_cycle_id",
        "risk_checks",
        ["cycle_id"],
        unique=False,
    )

    # 7. orders
    op.create_index(
        "ix_orders_cycle_id",
        "orders",
        ["cycle_id"],
        unique=False,
    )

    # 8. fills
    op.create_index(
        "ix_fills_order_id",
        "fills",
        ["order_id"],
        unique=False,
    )

    # 9. monitoring_events
    op.create_index(
        "ix_monitoring_events_cycle_id",
        "monitoring_events",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_events_fired_at",
        "monitoring_events",
        ["fired_at"],
        unique=False,
    )

    # 10. performance
    op.create_index(
        "ix_performance_cycle_id",
        "performance",
        ["cycle_id"],
        unique=False,
    )


def downgrade() -> None:
    # 10. performance
    op.drop_index("ix_performance_cycle_id", table_name="performance")

    # 9. monitoring_events
    op.drop_index("ix_monitoring_events_fired_at", table_name="monitoring_events")
    op.drop_index("ix_monitoring_events_cycle_id", table_name="monitoring_events")

    # 8. fills
    op.drop_index("ix_fills_order_id", table_name="fills")

    # 7. orders
    op.drop_index("ix_orders_cycle_id", table_name="orders")

    # 6. risk_checks
    op.drop_index("ix_risk_checks_cycle_id", table_name="risk_checks")

    # 5. strategy_decisions
    op.drop_index(
        "ix_strategy_decisions_selected_hypothesis_id",
        table_name="strategy_decisions",
    )
    op.drop_index("ix_strategy_decisions_cycle_id", table_name="strategy_decisions")

    # 4. strategy_hypotheses
    op.drop_index(
        "ix_strategy_hypotheses_cycle_id",
        table_name="strategy_hypotheses",
    )

    # 3. agent_runs
    op.drop_index("ix_agent_runs_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_cycle_id", table_name="agent_runs")

    # 2. positions
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_index("ix_positions_snapshot_id", table_name="positions")

    # 1. portfolio_snapshots
    op.drop_index("ix_portfolio_snapshots_ts", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_cycle_id", table_name="portfolio_snapshots")
