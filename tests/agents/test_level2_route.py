"""Level-2 reassessment re-enters the graph at STRATEGY_EVALUATION — task P7-BE-5 / issue #173.

Confirms:
1. ``build_reassessment_entry_state`` packages the fired trigger + the current
   hedge into the seed state (``reassessment`` request, ``reassessment_origin``).
2. The reassessment sub-graph's first executed node is ``STRATEGY_EVALUATION`` —
   ``INITIAL`` / ``ANALYZING`` are skipped.
3. A run carries the trigger reason all the way through and lands terminal at
   ``MONITORING`` without escalating a second time.
"""

from __future__ import annotations

import datetime as _dt
import json

import pytest

from backend.agents.monitoring.escalation import (
    REASSESSMENT_ENTRY_NODE,
    build_reassessment_entry_state,
    build_reassessment_graph,
    run_reassessment_cycle,
)
from backend.agents.orchestrator.nodes import OrchestratorDeps
from backend.models.common import OptionLeg
from backend.models.enums import OptionRight, OrderSide, StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState, TriggerObservation
from backend.models.reassessment import ReassessmentRequest

pytestmark = pytest.mark.unit


def _context() -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    return HedgeContext(
        cycle_id="cyc-l2-route",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05, drawdown_tolerance_pct=0.10, target_hedge_ratio=0.50
        ),
        portfolio_state=PortfolioState(
            total_value=100_000.0, cash=20_000.0, equity=80_000.0, buying_power=50_000.0,
            drawdown=-0.03, volatility=0.22, beta=1.05,
        ),
        market_state=MarketState(regime="NEUTRAL", vix=19.0, index_trend="SIDEWAYS"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=0.80,
            target_hedge_ratio=0.50,
            expiration=(now + _dt.timedelta(days=20)).date(),
            hedge_pnl=120.0,
            legs=[
                OptionLeg(
                    underlying="AAPL",
                    right=OptionRight.PUT,
                    side=OrderSide.BUY,
                    strike=150.0,
                    expiration=(now + _dt.timedelta(days=20)).date(),
                    quantity=4,
                )
            ],
        ),
    )


def _state() -> MonitoringState:
    now = _dt.datetime.now(_dt.timezone.utc)
    return MonitoringState(
        cycle_id="cyc-l2-route",
        as_of=now,
        active_triggers=[TriggerType.PORTFOLIO_DELTA],
        trigger_history=[
            TriggerObservation(
                trigger_type=TriggerType.PORTFOLIO_DELTA,
                observed_at=now,
                observed_value=0.30,
                threshold=0.05,
                detail="Hedge drift of 30% exceeded threshold of 5%",
            )
        ],
        reassessment_recommended=True,
    )


def _deps(decision: str = "NO_TRADE") -> OrchestratorDeps:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {"decision": decision, "selected_strategy": None, "rationale": "routing test", "confidence": 0.9}
    )
    return OrchestratorDeps(llm_client=fake)


def test_entry_state_carries_the_trigger_and_the_current_hedge() -> None:
    ctx, state = _context(), _state()

    entry = build_reassessment_entry_state(ctx, state)

    assert entry["hedge_context"] is ctx
    assert entry["reassessment_origin"] is True
    req = entry["reassessment"]
    assert isinstance(req, ReassessmentRequest)
    assert TriggerType.PORTFOLIO_DELTA in req.trigger_types
    assert "Hedge drift" in req.reason
    # the current hedge rides along
    assert req.current_hedge.active is True
    assert req.current_hedge.legs and req.current_hedge.legs[0].underlying == "AAPL"


def test_subgraph_first_node_is_strategy_evaluation() -> None:
    graph = build_reassessment_graph(_deps())
    out = graph.invoke(build_reassessment_entry_state(_context(), _state()))

    assert out["visited"][0] == REASSESSMENT_ENTRY_NODE == "STRATEGY_EVALUATION"
    assert "INITIAL" not in out["visited"]
    assert "ANALYZING" not in out["visited"]
    assert out["current_node"] == "MONITORING"  # terminal


def test_run_reassessment_cycle_lands_terminal_without_relooping() -> None:
    out = run_reassessment_cycle(_deps("NO_TRADE"), _context(), _state())

    assert out["visited"] == ["STRATEGY_EVALUATION", "MONITORING"]
    # the MONITORING node saw reassessment_origin and did not escalate again
    assert "reassessment_decision" not in out
    # the reason was carried into the run
    assert any("re-entering at STRATEGY_EVALUATION" in n for n in out["notes"])


def test_new_protection_selection_routes_on_to_risk_check() -> None:
    """An INCREASE-shaped reassessment (LLM picks a strategy) continues to RISK_CHECK."""
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PROTECTIVE_PUT",
            "rationale": "add protection",
            "confidence": 0.9,
            "verdict": "APPROVE",
        }
    )
    out = run_reassessment_cycle(OrchestratorDeps(llm_client=fake), _context(), _state())

    # STRATEGY_EVALUATION ran first; if a strategy was selected the path went on
    # to RISK_CHECK, otherwise it short-circuited to MONITORING — either way it
    # never re-enters INITIAL/ANALYZING.
    assert out["visited"][0] == "STRATEGY_EVALUATION"
    assert out["visited"][-1] == "MONITORING"
    assert "ANALYZING" not in out["visited"]
