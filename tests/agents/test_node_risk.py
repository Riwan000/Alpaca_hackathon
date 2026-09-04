"""``RISK_CHECK`` node — task P6-BE-4 / issue #150.

Confirms the node wraps the Phase 5 risk gate:
- an ``APPROVE`` / ``MODIFY`` verdict routes on to ``EXECUTION`` and persists one
  ``risk_checks`` row;
- a ``REJECT`` verdict routes to ``MONITORING`` and — fed straight into the
  ``EXECUTION`` node — never reaches the broker (no ``orders`` row);
- a strategy decision with no hypothesis (``NO_TRADE``) is a routed no-op;
- :func:`route_after_risk` reads the same decision.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.orchestrator.nodes import (
    OrchestratorDeps,
    execution_node,
    risk_check_node,
    route_after_risk,
    strategy_evaluation_node,
)
from backend.db.orders_repo import OrderRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.models.enums import RiskVerdict

pytestmark = pytest.mark.integration


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


def _select_strategy_state(golden_hedge_context) -> dict[str, Any]:
    """Run the strategy node (fake LLM picks PROTECTIVE_PUT) → a state with a
    real ``strategy_decision`` carrying a selected hypothesis."""
    fake = _fake_llm(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PROTECTIVE_PUT",
            "rationale": "best protection per dollar",
            "confidence": 0.9,
        }
    )
    node = strategy_evaluation_node(OrchestratorDeps(llm_client=fake))
    base = {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    return {**base, **node(base)}


def test_approve_routes_to_execution_and_persists_a_risk_check(
    migrated_engine, golden_hedge_context
) -> None:
    state = _select_strategy_state(golden_hedge_context)
    node = risk_check_node(
        OrchestratorDeps(engine=migrated_engine, llm_client=_fake_llm({"verdict": "APPROVE", "rationale": "clean"}))
    )

    out = node(state)

    assert out["risk_decision"].verdict is RiskVerdict.APPROVE
    assert out["route"] == "EXECUTION"
    assert route_after_risk({**state, **out}) == "EXECUTION"
    persisted = RiskCheckRepository(migrated_engine).for_cycle(golden_hedge_context.cycle_id)
    assert persisted is not None and persisted.verdict == "APPROVE"


def test_reject_routes_to_monitoring_and_never_executes(
    migrated_engine, golden_hedge_context
) -> None:
    state = _select_strategy_state(golden_hedge_context)
    risk = risk_check_node(
        OrchestratorDeps(
            engine=migrated_engine,
            llm_client=_fake_llm(
                {"verdict": "REJECT", "violations": ["qualitative concern"], "rationale": "no"}
            ),
        )
    )

    risk_out = risk(state)
    assert risk_out["risk_decision"].verdict is RiskVerdict.REJECT
    assert risk_out["route"] == "MONITORING"
    assert route_after_risk({**state, **risk_out}) == "MONITORING"

    # Feed the rejected decision straight into EXECUTION — it must not submit.
    class _Broker:
        def submit_order(self, _payload: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
            raise AssertionError("EXECUTION submitted an order for a REJECT decision")

    execution = execution_node(OrchestratorDeps(engine=migrated_engine, broker=_Broker()))
    exec_out = execution({**state, **risk_out})

    assert "execution_result" not in exec_out
    assert any("nothing submitted" in note for note in exec_out["notes"])
    assert OrderRepository(migrated_engine).count() == 0


def test_no_hypothesis_is_a_routed_noop(migrated_engine, golden_hedge_context) -> None:
    fake = _fake_llm(
        {"decision": "NO_TRADE", "selected_strategy": None, "rationale": "no", "confidence": 0.9}
    )
    strat = strategy_evaluation_node(OrchestratorDeps(llm_client=fake))
    base = {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    state = {**base, **strat(base)}

    out = risk_check_node(OrchestratorDeps(engine=migrated_engine))(state)

    assert "risk_decision" not in out
    assert out["route"] == "MONITORING"
    assert out["notes"]
    assert RiskCheckRepository(migrated_engine).for_cycle(golden_hedge_context.cycle_id) is None
