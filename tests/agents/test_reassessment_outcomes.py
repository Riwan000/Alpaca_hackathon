"""Reassessment outcomes are schema-bound — task P7-BE-6 / issue #174.

Confirms:
1. A stubbed LLM outcome resolves to exactly one of
   ``MAINTAIN`` / ``INCREASE`` / ``DECREASE`` / ``REMOVE`` / ``REPLACE`` / ``NO_TRADE``;
   an off-schema label falls back to the deterministic heuristic (still in scope).
2. A stabilization context yields ``DECREASE`` or ``REMOVE`` (the Confirm box).
3. The other context shapes map to their expected outcome.
"""

from __future__ import annotations

import datetime as _dt
import json

import pytest

from backend.agents.monitoring.reassessment import ReassessmentAgent
from backend.models.enums import HedgeAction, StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState, TriggerObservation
from backend.models.reassessment import REASSESSMENT_OUTCOMES, ReassessmentDecision

pytestmark = pytest.mark.unit


def _context(
    *,
    drawdown: float | None = -0.01,
    volatility: float | None = 0.12,
    vix: float | None = 15.0,
    hedge_active: bool = True,
    hedge_ratio: float | None = 0.80,
    target_hedge_ratio: float | None = 0.50,
) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    return HedgeContext(
        cycle_id="cyc-reassess",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05,
            drawdown_tolerance_pct=0.10,
            target_hedge_ratio=target_hedge_ratio,
        ),
        portfolio_state=PortfolioState(
            total_value=100_000.0,
            cash=20_000.0,
            equity=80_000.0,
            buying_power=50_000.0,
            drawdown=drawdown,
            volatility=volatility,
            beta=1.0,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=vix, index_trend="SIDEWAYS"),
        current_hedge=CurrentHedge(
            active=hedge_active,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target_hedge_ratio,
            expiration=(now + _dt.timedelta(days=25)).date(),
            hedge_pnl=180.0,
        ),
    )


def _state(*triggers: TriggerType) -> MonitoringState:
    now = _dt.datetime.now(_dt.timezone.utc)
    return MonitoringState(
        cycle_id="cyc-reassess",
        as_of=now,
        active_triggers=list(triggers),
        trigger_history=[
            TriggerObservation(trigger_type=t, observed_at=now, detail=f"{t.value} fired")
            for t in triggers
        ],
        reassessment_recommended=bool(triggers),
    )


def _stub(outcome: str, *, confidence: float = 0.8):
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {"outcome": outcome, "rationale": f"stub says {outcome}", "confidence": confidence}
    )
    return fake


def _broken_llm():
    """A client whose completion body is not JSON — forces the heuristic path."""
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = "sorry, no JSON here"
    return fake


# --------------------------------------------------------------------------- #
# 1. schema-bound outcome
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "label",
    ["MAINTAIN", "INCREASE", "DECREASE", "REMOVE", "REPLACE", "NO_TRADE"],
)
def test_stub_llm_outcome_is_one_of_the_six(label: str) -> None:
    decision = ReassessmentAgent().assess(
        _context(), _state(TriggerType.PORTFOLIO_DELTA), client=_stub(label)
    )
    assert isinstance(decision, ReassessmentDecision)
    assert decision.outcome is HedgeAction(label)
    assert decision.outcome in REASSESSMENT_OUTCOMES
    # round-trips through its own schema
    assert ReassessmentDecision.model_validate(decision.model_dump()).outcome is decision.outcome


def test_off_schema_label_falls_back_to_heuristic_in_scope() -> None:
    decision = ReassessmentAgent().assess(
        _context(), _state(TriggerType.PORTFOLIO_DELTA), client=_stub("NEW_HEDGE")
    )
    assert decision.outcome in REASSESSMENT_OUTCOMES
    assert "fallback" in decision.rationale.lower()


def test_out_of_scope_outcome_is_rejected_by_the_contract() -> None:
    with pytest.raises(ValueError):
        ReassessmentDecision(
            cycle_id="c", outcome=HedgeAction.NEW_HEDGE, rationale="nope"
        )


# --------------------------------------------------------------------------- #
# 2. Confirm — stabilization → DECREASE or REMOVE
# --------------------------------------------------------------------------- #


def test_stabilization_context_yields_decrease_or_remove() -> None:
    ctx = _context(drawdown=-0.005, volatility=0.11, vix=13.0, hedge_ratio=0.80, target_hedge_ratio=0.40)
    decision = ReassessmentAgent().assess(
        ctx, _state(TriggerType.PORTFOLIO_DELTA), client=_broken_llm()
    )
    assert decision.outcome in {HedgeAction.DECREASE, HedgeAction.REMOVE}


def test_fully_calm_context_yields_remove() -> None:
    ctx = _context(drawdown=-0.002, volatility=0.09, vix=12.0)
    decision = ReassessmentAgent().assess(
        ctx, _state(TriggerType.PORTFOLIO_DELTA), client=_broken_llm()
    )
    assert decision.outcome is HedgeAction.REMOVE


# --------------------------------------------------------------------------- #
# 3. other shapes
# --------------------------------------------------------------------------- #


def test_deepening_drawdown_yields_increase() -> None:
    ctx = _context(drawdown=-0.09, volatility=0.34, vix=32.0)
    decision = ReassessmentAgent().assess(
        ctx, _state(TriggerType.DRAWDOWN_LIMIT), client=_broken_llm()
    )
    assert decision.outcome is HedgeAction.INCREASE


def test_correlation_breakdown_yields_replace() -> None:
    decision = ReassessmentAgent().assess(
        _context(), _state(TriggerType.CORRELATION_BREAKDOWN), client=_broken_llm()
    )
    assert decision.outcome is HedgeAction.REPLACE


def test_expiration_only_yields_replace() -> None:
    decision = ReassessmentAgent().assess(
        _context(), _state(TriggerType.TIME_ELAPSED), client=_broken_llm()
    )
    assert decision.outcome is HedgeAction.REPLACE


def test_no_hedge_on_book_yields_no_trade() -> None:
    decision = ReassessmentAgent().assess(
        _context(hedge_active=False),
        _state(TriggerType.PORTFOLIO_DELTA),
        client=_broken_llm(),
    )
    assert decision.outcome is HedgeAction.NO_TRADE
