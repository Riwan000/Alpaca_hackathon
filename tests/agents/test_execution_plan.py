"""Execution Agent — ``ExecutionPlan`` build tests — task P5-BE-10 / issue #133.

Confirms:
- an APPROVE decision → a plan whose legs / quantities match the approved
  hypothesis exactly, MLEG order class for a multi-leg structure;
- a MODIFY decision's adjustments (size cut, limit-price tighten) are applied to
  the plan and the estimated cost is scaled pro-rata;
- a REJECT decision, a decision with no approved hypothesis, and a modification
  naming an unknown field are each refused.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.agents.execution import ExecutionPlanError, build_execution_plan
from backend.models.risk import RiskDecision
from backend.models.strategy import StrategyHypothesis

_SPREAD_LEGS: list[dict[str, Any]] = [
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
]


def _hypothesis(**overrides: Any) -> StrategyHypothesis:
    raw: dict[str, Any] = {
        "cycle_id": "cyc-exec-plan",
        "strategy": "PUT_SPREAD",
        "action": "NEW_HEDGE",
        "viable": True,
        "legs": _SPREAD_LEGS,
        "cost": 240.0,
        "rationale": "defined-risk downside protection within budget",
    }
    raw.update(overrides)
    return StrategyHypothesis.model_validate(raw)


def _decision(verdict: str, **overrides: Any) -> RiskDecision:
    raw: dict[str, Any] = {
        "cycle_id": "cyc-exec-plan",
        "verdict": verdict,
        "rationale": "risk gate outcome",
        "approved_hypothesis": _hypothesis().model_dump(mode="json"),
    }
    raw.update(overrides)
    return RiskDecision.model_validate(raw)


def test_approved_decision_plan_matches_hypothesis_legs() -> None:
    """APPROVE → plan legs / quantities are the approved hypothesis, verbatim."""
    hyp = _hypothesis()
    plan = build_execution_plan(_decision("APPROVE"), approval_id="risk-cyc-exec-plan")

    assert plan.cycle_id == "cyc-exec-plan"
    assert plan.approval_id == "risk-cyc-exec-plan"
    assert plan.strategy == hyp.strategy
    assert plan.order_class == "MLEG"
    assert [(leg.strike, leg.side.value, leg.quantity) for leg in plan.legs] == [
        (145.0, "BUY", 2),
        (140.0, "SELL", 2),
    ]
    assert plan.estimated_cost == pytest.approx(240.0)
    # net combo debit = 3.15 - 1.95
    assert plan.constraints.limit_price == pytest.approx(1.2)


def test_single_leg_plan_uses_single_order_class() -> None:
    """A lone-leg hypothesis produces a SINGLE order class, not MLEG."""
    hyp = _hypothesis(legs=[_SPREAD_LEGS[0]], cost=630.0)
    plan = build_execution_plan(
        _decision("APPROVE", approved_hypothesis=hyp.model_dump(mode="json")),
        approval_id="risk-x",
    )
    assert plan.order_class == "SINGLE"
    assert len(plan.legs) == 1


def test_modify_quantity_is_applied_and_cost_scaled() -> None:
    """MODIFY 'quantity' → every leg resized, estimated_cost scaled pro-rata."""
    decision = _decision(
        "MODIFY",
        modifications=[
            {"field": "quantity", "from_value": 2, "to_value": 1, "reason": "cap notional"}
        ],
    )
    plan = build_execution_plan(decision, approval_id="risk-x")

    assert [leg.quantity for leg in plan.legs] == [1, 1]
    # original 4 contracts → 2 contracts → half the cost
    assert plan.estimated_cost == pytest.approx(120.0)


def test_modify_per_leg_limit_price_is_applied() -> None:
    """MODIFY 'legs[0].limit_price' tightens just that leg's price."""
    decision = _decision(
        "MODIFY",
        modifications=[
            {
                "field": "legs[0].limit_price",
                "from_value": 3.15,
                "to_value": 3.0,
                "reason": "tighten entry",
            }
        ],
    )
    plan = build_execution_plan(decision, approval_id="risk-x")
    assert plan.legs[0].limit_price == pytest.approx(3.0)
    assert plan.legs[1].limit_price == pytest.approx(1.95)


def test_reject_decision_has_no_plan() -> None:
    decision = _decision(
        "REJECT",
        violations=["cost exceeds the hard budget"],
        approved_hypothesis=None,
    )
    with pytest.raises(ExecutionPlanError):
        build_execution_plan(decision, approval_id="risk-x")


def test_missing_approved_hypothesis_is_refused() -> None:
    decision = _decision("APPROVE", approved_hypothesis=None)
    with pytest.raises(ExecutionPlanError):
        build_execution_plan(decision, approval_id="risk-x")


def test_unknown_modification_field_is_not_silently_dropped() -> None:
    decision = _decision(
        "MODIFY",
        modifications=[
            {"field": "wingspan", "from_value": 1, "to_value": 2, "reason": "???"}
        ],
    )
    with pytest.raises(ExecutionPlanError):
        build_execution_plan(decision, approval_id="risk-x")
