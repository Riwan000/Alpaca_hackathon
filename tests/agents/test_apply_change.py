"""Apply-change path for a reassessment outcome — task P7-BE-7 / issue #175.

Confirms:
- ``DECREASE`` → a sell/close plan (legs inverted, smaller) that still clears the
  risk gate and lowers the hedge ratio;
- ``REMOVE`` → a full close (resulting ratio 0);
- ``REPLACE`` → a full close plus a ``reopen_recommended`` flag for the follow-up;
- a non-changing outcome (``MAINTAIN`` / ``NO_TRADE``) produces no plan;
- with a broker + engine the close is submitted and a signed ``hedge_changes``
  row is written.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import pytest

from backend.agents.monitoring.apply_change import apply_change, build_change_hypothesis
from backend.db.monitoring_repo import MonitoringRepository
from backend.db.orders_repo import OrderRepository
from backend.models.common import OptionLeg
from backend.models.enums import (
    ExecutionStatus,
    HedgeAction,
    OrderSide,
    OptionRight,
    RiskVerdict,
    StrategyType,
)
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.reassessment import ReassessmentDecision


def _context(*, hedge_ratio: float = 0.80, target: float = 0.40, qty: int = 4) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp = (now + _dt.timedelta(days=30)).date()
    return HedgeContext(
        cycle_id="cyc-apply",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05, drawdown_tolerance_pct=0.10, target_hedge_ratio=target
        ),
        portfolio_state=PortfolioState(
            total_value=250_000.0, cash=100_000.0, equity=150_000.0, buying_power=120_000.0,
            drawdown=-0.01, volatility=0.13, beta=1.0, gross_exposure=0.60,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=14.0, index_trend="UP"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target,
            expiration=exp,
            hedge_pnl=90.0,
            legs=[
                OptionLeg(
                    underlying="AAPL",
                    right=OptionRight.PUT,
                    side=OrderSide.BUY,
                    strike=150.0,
                    expiration=exp,
                    quantity=qty,
                )
            ],
        ),
    )


def _decision(outcome: HedgeAction, *, target: float | None = 0.40) -> ReassessmentDecision:
    return ReassessmentDecision(
        cycle_id="cyc-apply",
        outcome=outcome,
        rationale=f"{outcome.value} — market stabilized",
        current_hedge_ratio=0.80,
        target_hedge_ratio=target,
        confidence=0.7,
    )


def _approve_llm() -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps({"verdict": "APPROVE", "rationale": "reduces exposure"})
    return fake


class _FillingBroker:
    """Echoes a single-leg close payload back as fully filled."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return {
            "id": "close-1",
            "symbol": payload.get("symbol", "AAPL"),
            "side": payload.get("side", "sell"),
            "qty": payload.get("qty", "1"),
            "filled_qty": payload.get("qty", "1"),
            "filled_avg_price": "2.40",
            "status": "filled",
            "submitted_at": "2026-09-04T15:00:00Z",
            "filled_at": "2026-09-04T15:00:01Z",
        }


# --------------------------------------------------------------------------- #
# hypothesis shape
# --------------------------------------------------------------------------- #


def test_decrease_hypothesis_inverts_side_and_shrinks_quantity() -> None:
    hypo = build_change_hypothesis(_decision(HedgeAction.DECREASE), _context(qty=4))

    assert hypo.action is HedgeAction.DECREASE
    assert hypo.legs[0].side is OrderSide.SELL  # was BUY
    assert 1 <= hypo.legs[0].quantity < 4  # partial close
    assert hypo.cost == 0.0
    assert hypo.hedge_metrics.hedge_ratio < 0.80


def test_remove_hypothesis_closes_the_whole_leg() -> None:
    hypo = build_change_hypothesis(_decision(HedgeAction.REMOVE, target=0.0), _context(qty=4))

    assert hypo.legs[0].side is OrderSide.SELL
    assert hypo.legs[0].quantity == 4
    assert hypo.hedge_metrics.hedge_ratio == 0.0


# --------------------------------------------------------------------------- #
# apply_change — through the risk gate
# --------------------------------------------------------------------------- #


def test_decrease_produces_a_risk_cleared_reducing_plan() -> None:
    res = apply_change(_decision(HedgeAction.DECREASE), _context(), risk_client=_approve_llm())

    assert res.cleared_risk_gate is True
    assert res.risk_decision is not None and res.risk_decision.verdict in {
        RiskVerdict.APPROVE,
        RiskVerdict.MODIFY,
    }
    assert res.plan is not None
    assert res.plan.legs[0].side is OrderSide.SELL
    assert res.after_hedge_ratio is not None and res.after_hedge_ratio < res.before_hedge_ratio
    assert res.delta is not None and res.delta < 0


def test_decrease_clears_the_real_deterministic_gate() -> None:
    """No LLM stub — the deterministic engine should approve a reduce (it lowers
    every hard limit it checks)."""
    res = apply_change(_decision(HedgeAction.DECREASE), _context())
    assert res.risk_decision is not None
    assert res.risk_decision.verdict is not RiskVerdict.REJECT, res.notes
    assert res.plan is not None


def test_remove_produces_a_full_close_plan() -> None:
    res = apply_change(_decision(HedgeAction.REMOVE, target=0.0), _context(), risk_client=_approve_llm())

    assert res.plan is not None
    assert res.plan.legs[0].quantity == 4
    assert res.after_hedge_ratio == 0.0
    assert res.reopen_recommended is False


def test_replace_flags_a_follow_up_reopen() -> None:
    res = apply_change(_decision(HedgeAction.REPLACE, target=0.0), _context(), risk_client=_approve_llm())

    assert res.reopen_recommended is True
    assert res.plan is not None
    assert res.plan.legs[0].quantity == 4  # full close before the re-open
    assert any("REPLACE" in n for n in res.notes)


@pytest.mark.parametrize("outcome", [HedgeAction.MAINTAIN, HedgeAction.NO_TRADE])
def test_non_changing_outcome_produces_no_plan(outcome: HedgeAction) -> None:
    res = apply_change(_decision(outcome), _context())
    assert res.plan is None
    assert res.delta == 0.0
    assert any("no position change" in n for n in res.notes)


def test_missing_legs_is_reported_not_raised() -> None:
    ctx = _context()
    ctx = ctx.model_copy(
        update={"current_hedge": ctx.current_hedge.model_copy(update={"legs": []})}
    )
    res = apply_change(_decision(HedgeAction.DECREASE), ctx)
    assert res.plan is None
    assert any("no legs on record" in n for n in res.notes)


# --------------------------------------------------------------------------- #
# Confirm — a DECREASE results in a real (paper) order that reduces the hedge
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_decrease_submits_and_writes_a_signed_hedge_change(migrated_engine) -> None:
    broker = _FillingBroker()
    res = apply_change(
        _decision(HedgeAction.DECREASE),
        _context(),
        risk_client=_approve_llm(),
        engine=migrated_engine,
        broker=broker,
    )

    assert res.submitted is True
    assert res.execution_result is not None
    assert res.execution_result.status in {
        ExecutionStatus.FILLED,
        ExecutionStatus.PARTIALLY_FILLED,
    }
    assert broker.payloads  # an order was sent
    assert OrderRepository(migrated_engine).list_for_cycle("cyc-apply")

    changes = MonitoringRepository(migrated_engine).list_hedge_changes(cycle_id="cyc-apply")
    assert len(changes) == 1
    assert float(changes[0].delta) < 0  # the hedge was reduced
    assert float(changes[0].after_hedge_ratio) < float(changes[0].before_hedge_ratio)
    assert str(changes[0].action) == HedgeAction.DECREASE.value
