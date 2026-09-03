"""Deterministic risk engine — position / hedge-ratio / notional limits.

Task **P5-BE-2** (BRD §19). Three hard limits sit next to the hedge-budget gate:

* **max hedge ratio** — the proposal may not hedge past the policy ceiling;
* **max notional** — the gross option-leg notional may not exceed the book;
* **position limit** — option contracts on a name must be covered by the shares
  held in that name (no over-hedged or naked single-name bet).

Each limit breached on its own produces a *distinct*
:class:`~backend.agents.risk.codes.ViolationCode`; a plan exactly at a limit
passes. The confirm scenario rejects an over-hedged plan and reads back the
specific reason.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.agents.risk import (
    DEFAULT_MAX_HEDGE_RATIO,
    RiskEngineLimits,
    ViolationCode,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
    run_limit_checks,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-2"
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
    target_hedge_ratio: float | None = None,
    aapl_shares: float = 100.0,
    cycle_id: str = _CYCLE,
) -> HedgeContext:
    positions = []
    if aapl_shares:
        positions.append(
            {
                "symbol": "AAPL",
                "qty": aapl_shares,
                "avg_price": 150.0,
                "market_value": aapl_shares * 150.0,
                "asset_class": "EQUITY",
                "side": "BUY",
            }
        )
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": total_value / 4,
                "positions": positions,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
                "target_hedge_ratio": target_hedge_ratio,
            },
        }
    )


def _leg(
    *,
    underlying: str = "AAPL",
    strike: float = 145.0,
    quantity: int = 1,
    side: OrderSide = OrderSide.BUY,
    right: OptionRight = OptionRight.PUT,
) -> OptionLeg:
    return OptionLeg(
        underlying=underlying,
        right=right,
        side=side,
        strike=strike,
        expiration=date(2026, 10, 3),
        quantity=quantity,
    )


def _hypothesis(
    *,
    hedge_ratio: float | None = 0.5,
    cost: float = 250.0,
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
        hedge_metrics=HedgeMetrics(hedge_ratio=hedge_ratio),
        rationale="synthetic hypothesis for the limit-engine tests",
    )


# --------------------------------------------------------------------------- #
# violation codes are pinned
# --------------------------------------------------------------------------- #


def test_violation_code_string_values_are_pinned() -> None:
    assert ViolationCode.HEDGE_BUDGET_EXCEEDED.value == "HEDGE_BUDGET_EXCEEDED"
    assert ViolationCode.MAX_HEDGE_RATIO_EXCEEDED.value == "MAX_HEDGE_RATIO_EXCEEDED"
    assert ViolationCode.MAX_NOTIONAL_EXCEEDED.value == "MAX_NOTIONAL_EXCEEDED"
    assert ViolationCode.POSITION_LIMIT_EXCEEDED.value == "POSITION_LIMIT_EXCEEDED"


def test_default_hedge_ratio_ceiling_is_one() -> None:
    assert DEFAULT_MAX_HEDGE_RATIO == 1.0


# --------------------------------------------------------------------------- #
# max hedge ratio
# --------------------------------------------------------------------------- #


def test_over_max_hedge_ratio_fails_with_its_own_code() -> None:
    outcome = check_max_hedge_ratio(_hypothesis(hedge_ratio=1.5), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MAX_HEDGE_RATIO_EXCEEDED
    assert outcome.observed == pytest.approx(1.5)
    assert outcome.limit == pytest.approx(1.0)
    assert "hedge ratio" in outcome.detail


def test_hedge_ratio_exactly_at_the_ceiling_passes() -> None:
    outcome = check_max_hedge_ratio(_hypothesis(hedge_ratio=1.0), _context())

    assert outcome.passed is True
    assert outcome.code is None


def test_objective_target_raises_the_hedge_ratio_ceiling() -> None:
    # target 1.6 → a 1.5 ratio is now within policy
    ctx = _context(target_hedge_ratio=1.6)

    assert check_max_hedge_ratio(_hypothesis(hedge_ratio=1.5), ctx).passed is True


def test_missing_hedge_ratio_is_treated_as_zero() -> None:
    outcome = check_max_hedge_ratio(_hypothesis(hedge_ratio=None), _context())

    assert outcome.passed is True
    assert outcome.observed == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# max notional
# --------------------------------------------------------------------------- #


def test_over_max_notional_fails_with_its_own_code() -> None:
    # tiny book (10_000); one 145 put controls 145 * 100 = 14_500 of notional.
    ctx = _context(total_value=10_000.0)
    outcome = check_max_notional(_hypothesis(legs=(_leg(strike=145.0),)), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MAX_NOTIONAL_EXCEEDED
    assert outcome.observed == pytest.approx(14_500.0)
    assert outcome.limit == pytest.approx(10_000.0)
    assert "notional" in outcome.detail


def test_notional_exactly_at_the_cap_passes() -> None:
    # book worth exactly the leg notional: 145 * 100 = 14_500
    ctx = _context(total_value=14_500.0)
    outcome = check_max_notional(_hypothesis(legs=(_leg(strike=145.0),)), ctx)

    assert outcome.passed is True
    assert outcome.code is None


def test_no_leg_hypothesis_has_zero_notional() -> None:
    outcome = check_max_notional(_hypothesis(legs=()), _context(total_value=1.0))

    assert outcome.passed is True
    assert outcome.observed == pytest.approx(0.0)


def test_multi_leg_notional_sums_every_leg() -> None:
    ctx = _context(total_value=100_000.0)
    legs = (_leg(strike=145.0, quantity=1), _leg(strike=140.0, quantity=1, side=OrderSide.SELL))
    # (145 + 140) * 100 = 28_500
    assert check_max_notional(_hypothesis(legs=legs), ctx).observed == pytest.approx(
        28_500.0
    )


# --------------------------------------------------------------------------- #
# position limit — per-name share coverage
# --------------------------------------------------------------------------- #


def test_over_position_limit_fails_with_its_own_code() -> None:
    # 100 AAPL shares cover exactly 1 contract; propose 2.
    ctx = _context(aapl_shares=100.0)
    outcome = check_position_limit(_hypothesis(legs=(_leg(quantity=2),)), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.POSITION_LIMIT_EXCEEDED
    assert "AAPL" in outcome.detail
    assert outcome.observed == pytest.approx(2.0)
    assert outcome.limit == pytest.approx(1.0)


def test_hedging_a_name_not_held_breaches_the_position_limit() -> None:
    ctx = _context(aapl_shares=100.0)
    outcome = check_position_limit(
        _hypothesis(legs=(_leg(underlying="MSFT", quantity=1),)), ctx
    )

    assert outcome.passed is False
    assert outcome.code is ViolationCode.POSITION_LIMIT_EXCEEDED
    assert "MSFT" in outcome.detail
    assert outcome.limit == pytest.approx(0.0)


def test_position_exactly_covered_passes() -> None:
    ctx = _context(aapl_shares=100.0)
    outcome = check_position_limit(_hypothesis(legs=(_leg(quantity=1),)), ctx)

    assert outcome.passed is True
    assert outcome.code is None


def test_one_by_one_spread_on_a_covered_name_passes() -> None:
    # long + short leg, 1 contract each — the larger side is 1, covered by 100 shares.
    ctx = _context(aapl_shares=100.0)
    legs = (
        _leg(strike=145.0, quantity=1, side=OrderSide.BUY),
        _leg(strike=140.0, quantity=1, side=OrderSide.SELL),
    )
    assert check_position_limit(_hypothesis(legs=legs), ctx).passed is True


def test_naked_short_calls_beyond_coverage_breach_the_position_limit() -> None:
    ctx = _context(aapl_shares=100.0)
    legs = (_leg(right=OptionRight.CALL, side=OrderSide.SELL, quantity=2, strike=160.0),)
    outcome = check_position_limit(_hypothesis(legs=legs), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.POSITION_LIMIT_EXCEEDED


# --------------------------------------------------------------------------- #
# each limit breached individually → a distinct code
# --------------------------------------------------------------------------- #


def test_each_limit_breached_alone_yields_a_distinct_code() -> None:
    # ratio only: big book so notional/position are fine
    ctx = _context(total_value=1_000_000.0, aapl_shares=100.0)
    ratio_only = check_max_hedge_ratio(_hypothesis(hedge_ratio=2.0), ctx)

    # notional only: tiny book, ratio + position within limits
    small = _context(total_value=10_000.0, aapl_shares=100.0)
    notional_only = check_max_notional(
        _hypothesis(hedge_ratio=0.5, legs=(_leg(strike=145.0, quantity=1),)), small
    )

    # position only: big book, ratio fine, but 3 contracts on 100 shares
    position_only = check_position_limit(
        _hypothesis(hedge_ratio=0.5, legs=(_leg(quantity=3),)), ctx
    )

    codes = {ratio_only.code, notional_only.code, position_only.code}
    assert codes == {
        ViolationCode.MAX_HEDGE_RATIO_EXCEEDED,
        ViolationCode.MAX_NOTIONAL_EXCEEDED,
        ViolationCode.POSITION_LIMIT_EXCEEDED,
    }


# --------------------------------------------------------------------------- #
# run_limit_checks — the P5-BE-2 trio together
# --------------------------------------------------------------------------- #


def test_run_limit_checks_returns_one_outcome_per_limit_in_order() -> None:
    outcomes = run_limit_checks(_hypothesis(), _context())

    assert [o.name for o in outcomes] == [
        "max_hedge_ratio",
        "max_notional",
        "position_limit",
    ]


def test_run_limit_checks_all_clear_on_a_within_limits_plan() -> None:
    ctx = _context(total_value=1_000_000.0, aapl_shares=100.0)
    outcomes = run_limit_checks(_hypothesis(hedge_ratio=0.5, legs=(_leg(quantity=1),)), ctx)

    assert all(o.passed for o in outcomes)
    assert all(o.code is None for o in outcomes)


def test_a_plan_over_all_three_limits_is_rejected_with_three_distinct_codes() -> None:
    # tiny book, over-hedged ratio, 3 contracts on 100 shares
    ctx = _context(total_value=10_000.0, aapl_shares=100.0)
    bad = _hypothesis(hedge_ratio=3.0, legs=(_leg(strike=145.0, quantity=3),))

    outcomes = run_limit_checks(bad, ctx)
    failed = [o for o in outcomes if o.violated]

    assert len(failed) == 3
    assert {o.code for o in failed} == {
        ViolationCode.MAX_HEDGE_RATIO_EXCEEDED,
        ViolationCode.MAX_NOTIONAL_EXCEEDED,
        ViolationCode.POSITION_LIMIT_EXCEEDED,
    }


def test_custom_limits_flow_through_run_limit_checks() -> None:
    ctx = _context(total_value=1_000_000.0, aapl_shares=100.0)
    tight = replace(RiskEngineLimits.from_context(ctx), max_notional=1_000.0)

    outcomes = run_limit_checks(
        _hypothesis(hedge_ratio=0.5, legs=(_leg(strike=145.0, quantity=1),)),
        ctx,
        limits=tight,
    )
    by_name = {o.name: o for o in outcomes}

    assert by_name["max_notional"].violated is True
    assert by_name["max_notional"].code is ViolationCode.MAX_NOTIONAL_EXCEEDED
    assert by_name["max_hedge_ratio"].passed is True


# --------------------------------------------------------------------------- #
# audit-row mapping
# --------------------------------------------------------------------------- #


def test_limit_outcomes_map_to_the_position_limits_risk_check_category() -> None:
    ctx = _context()
    for outcome in run_limit_checks(_hypothesis(), ctx):
        check = outcome.to_risk_check()
        assert check.category == "POSITION_LIMITS"
        assert check.name == outcome.name


# --------------------------------------------------------------------------- #
# Confirm — a plan over max hedge ratio is rejected with that specific reason
# --------------------------------------------------------------------------- #


def _golden_context() -> HedgeContext:
    return HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))


def test_confirm_over_max_hedge_ratio_is_rejected_with_that_reason() -> None:
    ctx = _golden_context()  # objective.target_hedge_ratio = 0.8 → ceiling 1.0

    over_hedged = _hypothesis(
        hedge_ratio=1.35,
        legs=(_leg(quantity=1),),
        cycle_id=ctx.cycle_id,
    )

    outcome = check_max_hedge_ratio(over_hedged, ctx)

    assert outcome.violated is True
    assert outcome.code is ViolationCode.MAX_HEDGE_RATIO_EXCEEDED
    assert "hedge ratio" in outcome.detail.lower()
    assert outcome.observed == pytest.approx(1.35)
    assert outcome.limit == pytest.approx(1.0)

    # the other two limits are clean — the rejection is specific, not blanket
    others = {o.name: o for o in run_limit_checks(over_hedged, ctx)}
    assert others["max_notional"].passed is True
    assert others["position_limit"].passed is True
