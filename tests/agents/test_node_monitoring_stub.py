"""``MONITORING`` node (Phase 7 hand-off placeholder) — task P6-BE-6 / issue #152.

Confirms:
- the node is **terminal** for the cycle — it writes ``monitoring_state`` and
  leaves no ``route`` for a successor;
- it persists one ``monitoring_state`` row keyed to the cycle;
- the execution outcome (when present) rides along in the row ``detail``;
- with no engine it still returns a snapshot rather than crashing.
"""

from __future__ import annotations

import pytest

from backend.agents.orchestrator.nodes import OrchestratorDeps, monitoring_node
from backend.db.monitoring_repo import MonitoringRepository
from backend.models.enums import ExecutionStatus
from backend.models.execution import ExecutionResult
from backend.models.monitoring import MonitoringState

pytestmark = pytest.mark.integration


def test_terminal_node_persists_a_monitoring_state_row(
    migrated_engine, golden_hedge_context
) -> None:
    node = monitoring_node(OrchestratorDeps(engine=migrated_engine))

    out = node(
        {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    )

    snapshot = out["monitoring_state"]
    assert isinstance(snapshot, MonitoringState)
    assert snapshot.cycle_id == golden_hedge_context.cycle_id
    assert out["current_node"] == "MONITORING"
    assert out["visited"] == ["MONITORING"]
    assert "route" not in out  # terminal — nothing routes onward

    row = MonitoringRepository(migrated_engine).get_latest_state()
    assert row is not None
    assert row.cycle_id == golden_hedge_context.cycle_id
    assert row.monitoring_status == "ACTIVE"


def test_execution_outcome_rides_along_in_the_row_detail(
    migrated_engine, golden_hedge_context
) -> None:
    node = monitoring_node(OrchestratorDeps(engine=migrated_engine))

    node(
        {
            "cycle_id": golden_hedge_context.cycle_id,
            "hedge_context": golden_hedge_context,
            "execution_result": ExecutionResult(
                cycle_id=golden_hedge_context.cycle_id, status=ExecutionStatus.FILLED
            ),
        }
    )

    row = MonitoringRepository(migrated_engine).get_latest_state()
    assert row is not None
    assert row.detail is not None
    assert row.detail.get("execution_status") == "FILLED"


def test_runs_without_an_engine(golden_hedge_context) -> None:
    node = monitoring_node(OrchestratorDeps())

    out = node(
        {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    )

    assert isinstance(out["monitoring_state"], MonitoringState)
    assert out["current_node"] == "MONITORING"
