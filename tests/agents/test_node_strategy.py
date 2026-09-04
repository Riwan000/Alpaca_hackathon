"""``STRATEGY_EVALUATION`` node — task P6-BE-3 / issue #149.

Confirms the node wraps Phase 4:
- it consumes the state's :class:`HedgeContext` and writes a
  :class:`StrategyDecision`;
- a ``SELECT_STRATEGY`` outcome routes on to ``RISK_CHECK``;
- a ``NO_TRADE`` outcome routes toward ``MONITORING`` (nothing to risk-check);
- :func:`route_after_strategy` reads the same decision.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.orchestrator.nodes import (
    OrchestratorDeps,
    route_after_strategy,
    strategy_evaluation_node,
)
from backend.models.enums import DecisionType
from backend.models.strategy import StrategyDecision

pytestmark = pytest.mark.unit


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


def test_writes_a_strategy_decision_and_routes_to_risk_check(golden_hedge_context) -> None:
    fake = _fake_llm(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PROTECTIVE_PUT",
            "rationale": "best protection per dollar within budget",
            "confidence": 0.9,
        }
    )
    node = strategy_evaluation_node(OrchestratorDeps(llm_client=fake))

    out = node({"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context})

    decision = out["strategy_decision"]
    assert isinstance(decision, StrategyDecision)
    assert decision.decision is DecisionType.SELECT_STRATEGY
    assert out["route"] == "RISK_CHECK"
    assert out["current_node"] == "STRATEGY_EVALUATION"
    assert out["visited"] == ["STRATEGY_EVALUATION"]
    assert route_after_strategy(out) == "RISK_CHECK"


def test_no_trade_routes_toward_monitoring(golden_hedge_context) -> None:
    fake = _fake_llm(
        {
            "decision": "NO_TRADE",
            "selected_strategy": None,
            "rationale": "drawdown is inside tolerance; carry not worth it",
            "confidence": 0.85,
        }
    )
    node = strategy_evaluation_node(OrchestratorDeps(llm_client=fake))

    out = node({"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context})

    assert out["strategy_decision"].decision is DecisionType.NO_TRADE
    assert out["route"] == "MONITORING"
    assert any("MONITORING" in note for note in out["notes"])
    assert route_after_strategy(out) == "MONITORING"


def test_missing_context_is_an_error_routed_to_monitoring() -> None:
    node = strategy_evaluation_node(OrchestratorDeps())

    out = node({"cycle_id": "cyc-x"})

    assert "strategy_decision" not in out
    assert out["route"] == "MONITORING"
    assert any("STRATEGY_EVALUATION" in e for e in out["errors"])
