"""Deterministic risk engine — hedge-budget check — task P5-BE-1 (BRD §19).

The first hard gate of the Phase 5 safety layer: a hedge whose cash cost blows
the hedge budget is rejected here, before the LLM Risk Agent is ever called, and
the rejection carries the numbers. Cost exactly equal to the budget passes.

The confirm scenario runs a *real* strategy agent's viable proposal, starves the
budget, and asserts it is blocked by a plain pure function that never touches an
LLM.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.agents.risk import (
    CheckOutcome,
    RiskEngineLimits,
    ViolationCode,
    check_hedge_budget,
)
from backend.agents.strategies import ProtectivePutAgent
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskCheck
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-1"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)


def _context(
    *,
    total_value: float = 100_000.0,
    budget_pct: float = 0.05,
    cycle_id: str = _CYCLE,
) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": total_value / 4,
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
                "max_hedge_budget_pct": budget_pct,
                "drawdown_tolerance_pct": 0.10,
            },
        }
    )


def _leg(*, strike: float = 145.0, quantity: int = 1) -> OptionLeg:
    return OptionLeg(
        underlying="AAPL",
        right=OptionRight.PUT,
        side=OrderSide.BUY,
        strike=strike,
        expiration=date(2026, 10, 3),
        quantity=quantity,
    )


def _hypothesis(
    *,
    cost: float,
    legs: tuple[OptionLeg, ...] = (_leg(),),
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5),
        rationale="synthetic hypothesis for the hedge-budget check",
    )


# --------------------------------------------------------------------------- #
# cost > budget → fail with the numbers
# --------------------------------------------------------------------------- #


def test_cost_over_budget_fails_with_the_code_and_numbers() -> None:
    # budget = 0.05 * 100_000 = 5_000; a 6_000 debit is over.
    outcome = check_hedge_budget(_hypothesis(cost=6_000.0), _context())

    assert outcome.passed is False
    assert outcome.violated is True
    assert outcome.code is ViolationCode.HEDGE_BUDGET_EXCEEDED
    assert outcome.observed == pytest.approx(6_000.0)
    assert outcome.limit == pytest.approx(5_000.0)
    # the reason names both numbers and the overage
    assert "6,000" in outcome.detail
    assert "5,000" in outcome.detail
    assert "1,000" in outcome.detail


def test_cost_far_over_budget_still_a_single_clean_failure() -> None:
    outcome = check_hedge_budget(_hypothesis(cost=250_000.0), _context())

    assert outcome.code is ViolationCode.HEDGE_BUDGET_EXCEEDED
    assert outcome.limit == pytest.approx(5_000.0)


# --------------------------------------------------------------------------- #
# cost == budget → pass
# --------------------------------------------------------------------------- #


def test_cost_exactly_at_budget_passes() -> None:
    outcome = check_hedge_budget(_hypothesis(cost=5_000.0), _context())

    assert outcome.passed is True
    assert outcome.code is None
    assert outcome.observed == pytest.approx(5_000.0)
    assert outcome.limit == pytest.approx(5_000.0)


def test_cost_under_budget_passes() -> None:
    assert check_hedge_budget(_hypothesis(cost=1.0), _context()).passed is True


def test_zero_cost_no_hedge_passes() -> None:
    outcome = check_hedge_budget(_hypothesis(cost=0.0, legs=()), _context())

    assert outcome.passed is True
    assert outcome.code is None


# --------------------------------------------------------------------------- #
# budget derivation + overrides
# --------------------------------------------------------------------------- #


def test_budget_is_derived_from_objective_and_total_value() -> None:
    ctx = _context(total_value=200_000.0, budget_pct=0.01)  # budget = 2_000

    assert check_hedge_budget(_hypothesis(cost=2_000.0), ctx).passed is True
    assert check_hedge_budget(_hypothesis(cost=2_000.01), ctx).passed is False


def test_custom_limits_override_the_context_budget() -> None:
    ctx = _context()  # context budget would be 5_000
    tight = replace(RiskEngineLimits.from_context(ctx), hedge_budget=1_000.0)

    outcome = check_hedge_budget(_hypothesis(cost=4_000.0), ctx, limits=tight)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.HEDGE_BUDGET_EXCEEDED
    assert outcome.limit == pytest.approx(1_000.0)


# --------------------------------------------------------------------------- #
# audit-row mapping
# --------------------------------------------------------------------------- #


def test_failed_outcome_maps_to_a_risk_check_contract() -> None:
    outcome = check_hedge_budget(_hypothesis(cost=9_000.0), _context())
    check = outcome.to_risk_check()

    assert isinstance(check, RiskCheck)
    assert check.passed is False
    assert check.category == "COST"
    assert check.name == "hedge_budget"
    assert check.observed == pytest.approx(9_000.0)
    assert check.limit == pytest.approx(5_000.0)
    assert check.detail


def test_passing_outcome_maps_to_a_risk_check_contract() -> None:
    check = check_hedge_budget(_hypothesis(cost=10.0), _context()).to_risk_check()

    assert check.passed is True
    assert check.category == "COST"


def test_a_failing_outcome_must_carry_a_code() -> None:
    with pytest.raises(ValueError, match="failing check must carry a violation code"):
        CheckOutcome(name="hedge_budget", category="COST", passed=False)


def test_a_passing_outcome_must_not_carry_a_code() -> None:
    with pytest.raises(ValueError, match="passing check cannot carry a violation code"):
        CheckOutcome(
            name="hedge_budget",
            category="COST",
            passed=True,
            code=ViolationCode.HEDGE_BUDGET_EXCEEDED,
        )


# --------------------------------------------------------------------------- #
# Confirm — an over-budget plan is blocked before any LLM call
# --------------------------------------------------------------------------- #


def _golden_context() -> HedgeContext:
    return HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))


def test_confirm_real_agent_over_budget_proposal_is_blocked_pre_llm() -> None:
    ctx = _golden_context()

    # The protective put is genuinely viable on the seed context (~$315).
    put = ProtectivePutAgent().propose(ctx)
    assert put.viable is True
    assert put.cost > 0

    # Starve the hedge budget to $100 — the real proposal is now over.
    starved = replace(RiskEngineLimits.from_context(ctx), hedge_budget=100.0)

    outcome = check_hedge_budget(put, ctx, limits=starved)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.HEDGE_BUDGET_EXCEEDED
    assert outcome.observed == pytest.approx(put.cost)
    assert outcome.limit == pytest.approx(100.0)
    # `check_hedge_budget` is a pure function — no client argument, no I/O — so a
    # rejection here is inherently reached before the LLM Risk Agent (P5-BE-8).


def test_confirm_within_budget_the_same_proposal_passes() -> None:
    ctx = _golden_context()
    put = ProtectivePutAgent().propose(ctx)

    assert check_hedge_budget(put, ctx).passed is True
