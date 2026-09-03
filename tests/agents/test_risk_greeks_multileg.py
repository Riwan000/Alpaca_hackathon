"""Deterministic risk engine — net-delta bounds + multi-leg consistency — P5-BE-5.

Two hard gates beside the P5-BE-1/2 limits (BRD §19):

* **net-delta bounds** — a hedge overlay may not add net-long directional
  exposure, nor over-hedge past the shares it covers; a proposal whose
  ``hedge_metrics.net_delta`` is unset is not evaluated;
* **multi-leg consistency** — a put spread needs two puts with the long strike
  above the short strike, a collar needs both a long put and a short call, and
  no structure may span underlyings.

The confirm scenario rejects a malformed two-leg plan (a collar missing a leg).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.agents.risk import (
    DELTA_TOLERANCE_SHARES,
    NetDeltaBounds,
    ViolationCode,
    check_multileg_consistency,
    check_net_delta_bounds,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-5"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = date(2026, 10, 3)


def _context(*, aapl_shares: float = 100.0, extra: tuple[dict, ...] = ()) -> HedgeContext:
    positions: list[dict] = []
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
    positions.extend(extra)
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": positions,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
        }
    )


def _leg(
    *,
    underlying: str = "AAPL",
    right: OptionRight = OptionRight.PUT,
    side: OrderSide = OrderSide.BUY,
    strike: float = 145.0,
    quantity: int = 1,
) -> OptionLeg:
    return OptionLeg(
        underlying=underlying,
        right=right,
        side=side,
        strike=strike,
        expiration=_EXPIRY,
        quantity=quantity,
    )


def _hypothesis(
    *,
    strategy: StrategyType = StrategyType.PROTECTIVE_PUT,
    net_delta: float | None = -35.0,
    legs: tuple[OptionLeg, ...] = (_leg(),),
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=_CYCLE,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=315.0,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5, net_delta=net_delta),
        rationale="synthetic hypothesis for the P5-BE-5 screens",
    )


# --------------------------------------------------------------------------- #
# net-delta bounds
# --------------------------------------------------------------------------- #


def test_net_delta_inside_the_band_passes() -> None:
    outcome = check_net_delta_bounds(_hypothesis(net_delta=-35.0), _context())

    assert outcome.passed is True
    assert outcome.code is None


def test_net_delta_over_hedging_fails_below_the_lower_bound() -> None:
    # 100 AAPL shares → band ≈ [-125, 25]; -900 over-hedges the position.
    outcome = check_net_delta_bounds(_hypothesis(net_delta=-900.0), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.NET_DELTA_OUT_OF_BOUNDS
    assert outcome.observed == pytest.approx(-900.0)
    assert outcome.limit == pytest.approx(-125.0)
    assert "over-hedges" in outcome.detail


def test_net_delta_adding_long_exposure_fails_above_the_upper_bound() -> None:
    outcome = check_net_delta_bounds(_hypothesis(net_delta=200.0), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.NET_DELTA_OUT_OF_BOUNDS
    assert outcome.limit == pytest.approx(25.0)
    assert "net-long" in outcome.detail


def test_missing_net_delta_is_not_evaluated() -> None:
    outcome = check_net_delta_bounds(_hypothesis(net_delta=None), _context())

    assert outcome.passed is True
    assert "not computed" in outcome.detail


def test_net_delta_exactly_on_each_bound_passes() -> None:
    ctx = _context()
    assert check_net_delta_bounds(_hypothesis(net_delta=-125.0), ctx).passed is True
    assert check_net_delta_bounds(_hypothesis(net_delta=25.0), ctx).passed is True


def test_custom_bounds_override_the_context_band() -> None:
    tight = NetDeltaBounds(lower=-10.0, upper=10.0)
    outcome = check_net_delta_bounds(_hypothesis(net_delta=-35.0), _context(), bounds=tight)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.NET_DELTA_OUT_OF_BOUNDS
    assert outcome.limit == pytest.approx(-10.0)


def test_band_is_symmetric_at_the_tolerance_when_no_shares_are_held() -> None:
    band = NetDeltaBounds.from_context(_hypothesis(), _context(aapl_shares=0.0))

    assert band.lower == pytest.approx(-DELTA_TOLERANCE_SHARES)
    assert band.upper == pytest.approx(DELTA_TOLERANCE_SHARES)


def test_net_delta_outcome_maps_to_the_options_category() -> None:
    check = check_net_delta_bounds(_hypothesis(), _context()).to_risk_check()
    assert check.category == "OPTIONS"
    assert check.name == "net_delta_bounds"


# --------------------------------------------------------------------------- #
# multi-leg consistency
# --------------------------------------------------------------------------- #


def _put_spread(*, long_strike: float, short_strike: float) -> tuple[OptionLeg, ...]:
    return (
        _leg(right=OptionRight.PUT, side=OrderSide.BUY, strike=long_strike),
        _leg(right=OptionRight.PUT, side=OrderSide.SELL, strike=short_strike),
    )


def _collar(*, put_strike: float, call_strike: float) -> tuple[OptionLeg, ...]:
    return (
        _leg(right=OptionRight.PUT, side=OrderSide.BUY, strike=put_strike),
        _leg(right=OptionRight.CALL, side=OrderSide.SELL, strike=call_strike),
    )


def test_valid_put_spread_passes() -> None:
    plan = _hypothesis(
        strategy=StrategyType.PUT_SPREAD,
        legs=_put_spread(long_strike=145.0, short_strike=140.0),
    )
    assert check_multileg_consistency(plan, _context()).passed is True


def test_inverted_put_spread_strikes_fail() -> None:
    plan = _hypothesis(
        strategy=StrategyType.PUT_SPREAD,
        legs=_put_spread(long_strike=140.0, short_strike=145.0),
    )
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT
    assert "inverted" in outcome.detail


def test_put_spread_without_a_short_leg_fails() -> None:
    plan = _hypothesis(
        strategy=StrategyType.PUT_SPREAD,
        legs=(
            _leg(right=OptionRight.PUT, side=OrderSide.BUY, strike=145.0),
            _leg(right=OptionRight.CALL, side=OrderSide.BUY, strike=150.0),
        ),
    )
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT


def test_valid_collar_passes() -> None:
    plan = _hypothesis(
        strategy=StrategyType.COLLAR,
        legs=_collar(put_strike=140.0, call_strike=160.0),
    )
    assert check_multileg_consistency(plan, _context()).passed is True


def test_collar_missing_the_short_call_fails() -> None:
    plan = _hypothesis(
        strategy=StrategyType.COLLAR,
        legs=(
            _leg(right=OptionRight.PUT, side=OrderSide.BUY, strike=140.0),
            _leg(right=OptionRight.PUT, side=OrderSide.SELL, strike=135.0),
        ),
    )
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT
    assert "short call" in outcome.detail


def test_collar_with_inverted_strikes_fails() -> None:
    plan = _hypothesis(
        strategy=StrategyType.COLLAR,
        legs=_collar(put_strike=160.0, call_strike=150.0),
    )
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert "inverted" in outcome.detail


def test_legs_spanning_two_underlyings_fail() -> None:
    plan = _hypothesis(
        strategy=StrategyType.PUT_SPREAD,
        legs=(
            _leg(underlying="AAPL", right=OptionRight.PUT, side=OrderSide.BUY, strike=145.0),
            _leg(underlying="MSFT", right=OptionRight.PUT, side=OrderSide.SELL, strike=140.0),
        ),
    )
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT
    assert "underlying" in outcome.detail


def test_no_hedge_with_legs_is_inconsistent() -> None:
    plan = _hypothesis(strategy=StrategyType.NO_HEDGE, legs=(_leg(),))
    outcome = check_multileg_consistency(plan, _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT


def test_no_hedge_without_legs_passes() -> None:
    plan = _hypothesis(strategy=StrategyType.NO_HEDGE, net_delta=None, legs=())
    assert check_multileg_consistency(plan, _context()).passed is True


def test_single_leg_protective_put_passes() -> None:
    assert check_multileg_consistency(_hypothesis(), _context()).passed is True


def test_multileg_outcome_maps_to_the_options_category() -> None:
    plan = _hypothesis(
        strategy=StrategyType.PUT_SPREAD,
        legs=_put_spread(long_strike=145.0, short_strike=140.0),
    )
    check = check_multileg_consistency(plan, _context()).to_risk_check()
    assert check.category == "OPTIONS"
    assert check.name == "multileg_consistency"


# --------------------------------------------------------------------------- #
# Confirm — a malformed 2-leg plan is rejected for inconsistency
# --------------------------------------------------------------------------- #


def test_confirm_malformed_two_leg_plan_is_rejected_for_inconsistency() -> None:
    # A collar declared with two puts — the short call is simply missing.
    malformed = _hypothesis(
        strategy=StrategyType.COLLAR,
        net_delta=-40.0,
        legs=(
            _leg(right=OptionRight.PUT, side=OrderSide.BUY, strike=140.0),
            _leg(right=OptionRight.PUT, side=OrderSide.SELL, strike=130.0),
        ),
    )

    outcome = check_multileg_consistency(malformed, _context())

    assert outcome.violated is True
    assert outcome.code is ViolationCode.MULTILEG_INCONSISTENT
    assert "collar" in outcome.detail.lower()
    # net delta on the same plan is within band — the rejection is specific.
    assert check_net_delta_bounds(malformed, _context()).passed is True
