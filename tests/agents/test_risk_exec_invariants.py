"""P5-BE-16 — cross-agent invariants for the risk gate and the execution path.

Consolidated *test task* for **P5-BE-8** (Risk Agent) and **P5-BE-13**
(partial-fill recovery). Two things must stay true once the risk gate and the
Execution Agent are composed:

1. *A deterministic reject blocks an LLM approve.* When the risk checklist
   hard-fails, :meth:`RiskAgent.review` returns ``REJECT`` without ever
   consulting the LLM, and that :class:`RiskDecision` cannot be turned into an
   :class:`ExecutionPlan` — so no order is built. An approving stub LLM changes
   nothing. The clean-plan control shows the gate is not simply always blocking.
2. *A partial fill yields a truthful result.* :func:`build_execution_result`
   never labels a combo ``FILLED`` while a leg shows no fill: the unfilled leg
   lands in ``failed_legs`` and a ``recovery_action`` is recorded — even when the
   broker's own order header claims success.

Confirm (issue #139):
``pytest tests/agents/test_risk_agent.py tests/agents/test_partial_fill.py -q``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import pytest

from backend.agents.execution import (
    RECOVERY_CANCEL_UNFILLED_LEGS,
    RECOVERY_UNWIND_FILLED_LEGS,
    ExecutionPlanError,
    build_execution_plan,
    build_execution_result,
)
from backend.agents.risk import RiskAgent
from backend.models.common import OptionLeg
from backend.models.enums import (
    ExecutionStatus,
    HedgeAction,
    OptionRight,
    OrderSide,
    RiskVerdict,
    StrategyType,
)
from backend.models.execution import ExecutionPlan
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskDecision
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = date(2026, 10, 3)
_CYCLE = "cyc-p5-be-16"
_LONG = "AAPL261003P00145000"
_SHORT = "AAPL261003P00140000"


# --------------------------------------------------------------------------- #
# invariant 1 — a deterministic reject blocks an LLM approve
# --------------------------------------------------------------------------- #


def _context() -> HedgeContext:
    """A book + candidate that clears every P5-BE-1..6 deterministic check."""
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 60_000.0,
                "positions": [
                    {
                        "symbol": "AAPL",
                        "qty": 100.0,
                        "avg_price": 150.0,
                        "market_value": 15_000.0,
                        "asset_class": "EQUITY",
                        "side": "BUY",
                    }
                ],
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": [
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "strike": 145.0,
                    "expiration": _EXPIRY.isoformat(),
                    "premium": 3.15,
                    "bid": 3.1,
                    "ask": 3.2,
                    "open_interest": 4200,
                    "volume": 900,
                    "delta": -0.35,
                    "iv": 0.3,
                    "liquidity": "high",
                }
            ],
        }
    )


def _hypothesis(*, cost: float = 250.0) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=_CYCLE,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=[
            OptionLeg(
                underlying="AAPL",
                right=OptionRight.PUT,
                side=OrderSide.BUY,
                strike=145.0,
                expiration=_EXPIRY,
                quantity=1,
            )
        ],
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5),
        rationale="synthetic hypothesis for the P5-BE-16 invariants",
    )


def _llm_approve() -> str:
    return json.dumps(
        {
            "verdict": "APPROVE",
            "rationale": "nothing the checklist missed",
            "modifications": [],
            "violations": [],
            "warnings": [],
        }
    )


@pytest.mark.unit
def test_deterministic_reject_blocks_execution_even_when_llm_approves(mock_llm) -> None:
    """Hard budget fail → REJECT, LLM never consulted, and no plan can be built."""
    mock_llm.response_content = _llm_approve()

    # hedge budget = 5% of 100k = 5_000; a 40_000 debit is a hard fail.
    decision = RiskAgent(client=mock_llm).review(_hypothesis(cost=40_000.0), _context())

    assert decision.verdict is RiskVerdict.REJECT
    assert decision.approved_hypothesis is None
    assert decision.violations  # >= 1 deterministic violation
    assert mock_llm.calls == []  # the approving stub was never reached

    with pytest.raises(ExecutionPlanError):
        build_execution_plan(decision, approval_id=f"risk-{_CYCLE}")

    RiskDecision.model_validate(decision.model_dump())


@pytest.mark.unit
def test_clean_plan_llm_approve_flows_through_to_a_plan(mock_llm) -> None:
    """Control: a deterministically-clean plan the LLM approves does reach a plan."""
    mock_llm.response_content = _llm_approve()

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.APPROVE
    assert decision.approved_hypothesis is not None

    plan = build_execution_plan(decision, approval_id=f"risk-{_CYCLE}")

    assert plan.approval_id == f"risk-{_CYCLE}"
    assert plan.strategy == decision.approved_hypothesis.strategy
    assert [(leg.strike, leg.side.value, leg.quantity) for leg in plan.legs] == [
        (145.0, "BUY", 1)
    ]


# --------------------------------------------------------------------------- #
# invariant 2 — a partial fill yields a truthful result
# --------------------------------------------------------------------------- #


def _spread_plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "cycle_id": _CYCLE,
            "approval_id": f"risk-{_CYCLE}",
            "strategy": "PUT_SPREAD",
            "legs": [
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "side": "BUY",
                    "strike": 145.0,
                    "expiration": "2026-10-03",
                    "quantity": 2,
                    "limit_price": 3.15,
                },
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "side": "SELL",
                    "strike": 140.0,
                    "expiration": "2026-10-03",
                    "quantity": 2,
                    "limit_price": 1.95,
                },
            ],
            "order_class": "MLEG",
            "constraints": {"limit_price": 1.2},
            "estimated_cost": 240.0,
        }
    )


def _combo_order(*, header_status: str, long_fill: float, short_fill: float) -> dict[str, Any]:
    def _leg(symbol: str, side: str, filled: float, price: str) -> dict[str, Any]:
        if filled >= 2:
            status = "filled"
        elif filled:
            status = "partially_filled"
        else:
            status = "canceled"
        return {
            "symbol": symbol,
            "side": side,
            "qty": "2",
            "filled_qty": str(filled),
            "filled_avg_price": price if filled else "",
            "status": status,
            "filled_at": "2026-09-03T14:35:01Z",
        }

    return {
        "id": "combo-p5-be-16",
        "status": header_status,
        "submitted_at": "2026-09-03T14:35:00Z",
        "filled_at": "2026-09-03T14:35:02Z",
        "legs": [
            _leg(_LONG, "buy", long_fill, "3.20"),
            _leg(_SHORT, "sell", short_fill, "1.90"),
        ],
    }


@pytest.mark.unit
def test_partial_fill_is_partially_filled_never_filled() -> None:
    result = build_execution_result(
        _spread_plan(),
        _combo_order(header_status="partially_filled", long_fill=2, short_fill=0),
    )

    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert result.status is not ExecutionStatus.FILLED
    assert [fl.leg_symbol for fl in result.filled_legs] == [_LONG]
    assert [fl.leg_symbol for fl in result.failed_legs] == [_SHORT]
    assert result.recovery_action == RECOVERY_CANCEL_UNFILLED_LEGS


@pytest.mark.unit
def test_naked_short_partial_fill_recovers_by_unwinding() -> None:
    """Short leg filled, long protection did not → unwind the naked short."""
    result = build_execution_result(
        _spread_plan(),
        _combo_order(header_status="partially_filled", long_fill=0, short_fill=2),
    )

    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert [fl.leg_symbol for fl in result.failed_legs] == [_LONG]
    assert result.recovery_action == RECOVERY_UNWIND_FILLED_LEGS


@pytest.mark.unit
def test_broker_header_claiming_filled_is_downgraded_when_a_leg_has_no_fill() -> None:
    """The per-leg fills are the source of truth, not the order header."""
    result = build_execution_result(
        _spread_plan(),
        _combo_order(header_status="filled", long_fill=2, short_fill=0),
    )

    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert _SHORT in {fl.leg_symbol for fl in result.failed_legs}
    assert result.recovery_action != "NONE"
