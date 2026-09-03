"""Deterministic risk engine — buying-power + liquidity screens — task P5-BE-3.

Two hard gates beside the P5-BE-1/2 limits (BRD §19):

* **buying power** — the hedge's cash cost may not exceed available buying
  power; cost exactly equal to buying power passes;
* **liquidity** — a hedge leg with no quotes is rejected outright, a spread or
  open interest past the hard threshold is rejected, and a wide-but-tradeable
  leg is a warning, not a block.

The confirm scenario prices a leg on a strike the Options Analysis Agent never
surfaced and asserts it is rejected as illiquid.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.agents.risk import (
    LiquidityThresholds,
    ViolationCode,
    check_buying_power,
    check_liquidity,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-3"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = date(2026, 10, 3)


def _candidate(
    *,
    strike: float = 145.0,
    bid: float | None = 3.1,
    ask: float | None = 3.2,
    open_interest: int | None = 4200,
    right: OptionRight = OptionRight.PUT,
) -> dict:
    return {
        "underlying": "AAPL",
        "right": right.value,
        "strike": strike,
        "expiration": _EXPIRY.isoformat(),
        "premium": 3.15,
        "bid": bid,
        "ask": ask,
        "open_interest": open_interest,
        "volume": 900,
    }


def _context(
    *,
    buying_power: float = 50_000.0,
    candidates: tuple[dict, ...] = (_candidate(),),
) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": buying_power,
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
            "option_candidates": list(candidates),
        }
    )


def _leg(
    *,
    strike: float = 145.0,
    right: OptionRight = OptionRight.PUT,
    side: OrderSide = OrderSide.BUY,
    quantity: int = 1,
) -> OptionLeg:
    return OptionLeg(
        underlying="AAPL",
        right=right,
        side=side,
        strike=strike,
        expiration=_EXPIRY,
        quantity=quantity,
    )


def _hypothesis(
    *,
    cost: float = 315.0,
    legs: tuple[OptionLeg, ...] = (_leg(),),
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=_CYCLE,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5),
        rationale="synthetic hypothesis for the P5-BE-3 screens",
    )


# --------------------------------------------------------------------------- #
# buying power
# --------------------------------------------------------------------------- #


def test_cost_over_buying_power_fails_with_the_code_and_numbers() -> None:
    outcome = check_buying_power(_hypothesis(cost=60_000.0), _context(buying_power=50_000.0))

    assert outcome.passed is False
    assert outcome.code is ViolationCode.INSUFFICIENT_BUYING_POWER
    assert outcome.observed == pytest.approx(60_000.0)
    assert outcome.limit == pytest.approx(50_000.0)
    assert "10,000" in outcome.detail  # the shortfall


def test_cost_exactly_at_buying_power_passes() -> None:
    outcome = check_buying_power(_hypothesis(cost=50_000.0), _context(buying_power=50_000.0))

    assert outcome.passed is True
    assert outcome.code is None


def test_cost_under_buying_power_passes() -> None:
    assert check_buying_power(_hypothesis(cost=1.0), _context()).passed is True


def test_buying_power_override_is_honoured() -> None:
    outcome = check_buying_power(
        _hypothesis(cost=4_000.0), _context(buying_power=50_000.0), buying_power=1_000.0
    )

    assert outcome.passed is False
    assert outcome.limit == pytest.approx(1_000.0)


def test_buying_power_outcome_maps_to_the_cost_category() -> None:
    check = check_buying_power(_hypothesis(cost=9.0), _context()).to_risk_check()
    assert check.category == "COST"
    assert check.name == "buying_power"


# --------------------------------------------------------------------------- #
# liquidity — quotes present and inside the thresholds
# --------------------------------------------------------------------------- #


def test_liquid_leg_passes_clean() -> None:
    outcome = check_liquidity(_hypothesis(), _context())

    assert outcome.passed is True
    assert outcome.warning is False
    assert outcome.code is None


def test_leg_with_no_matching_candidate_is_rejected_as_illiquid() -> None:
    # propose a 150 strike; the only candidate is the 145.
    outcome = check_liquidity(_hypothesis(legs=(_leg(strike=150.0),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT
    assert "no quotes" in outcome.detail


def test_leg_matched_but_two_sided_quote_missing_is_illiquid() -> None:
    ctx = _context(candidates=(_candidate(bid=None, ask=None),))
    outcome = check_liquidity(_hypothesis(), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT


def test_spread_past_the_hard_threshold_fails() -> None:
    # bid 3.0 / ask 3.5 → mid 3.25, spread 0.5 → ~15.4% of mid > 10%.
    ctx = _context(candidates=(_candidate(bid=3.0, ask=3.5),))
    outcome = check_liquidity(_hypothesis(), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT
    assert outcome.observed == pytest.approx(0.5 / 3.25)
    assert outcome.limit == pytest.approx(0.10)


def test_spread_in_the_warn_band_is_a_warning_not_a_block() -> None:
    # bid 3.0 / ask 3.2 → mid 3.1, spread 0.2 → ~6.5% of mid: > 5%, < 10%.
    ctx = _context(candidates=(_candidate(bid=3.0, ask=3.2, open_interest=4200),))
    outcome = check_liquidity(_hypothesis(), ctx)

    assert outcome.passed is True
    assert outcome.warning is True
    assert "wide" in outcome.detail


def test_open_interest_below_the_floor_fails() -> None:
    ctx = _context(candidates=(_candidate(open_interest=50),))
    outcome = check_liquidity(_hypothesis(), ctx)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT
    assert outcome.observed == pytest.approx(50.0)
    assert outcome.limit == pytest.approx(100.0)


def test_thin_open_interest_above_the_floor_is_a_warning() -> None:
    ctx = _context(candidates=(_candidate(open_interest=300),))
    outcome = check_liquidity(_hypothesis(), ctx)

    assert outcome.passed is True
    assert outcome.warning is True
    assert "thin" in outcome.detail


def test_custom_thresholds_flow_through() -> None:
    strict = LiquidityThresholds(min_open_interest=5_000)
    outcome = check_liquidity(_hypothesis(), _context(), thresholds=strict)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT
    assert outcome.limit == pytest.approx(5_000.0)


def test_liquidity_outcome_maps_to_the_options_category() -> None:
    check = check_liquidity(_hypothesis(), _context()).to_risk_check()
    assert check.category == "OPTIONS"
    assert check.name == "liquidity"


def test_no_legs_is_trivially_liquid() -> None:
    assert check_liquidity(_hypothesis(legs=()), _context()).passed is True


# --------------------------------------------------------------------------- #
# Confirm — a strike with no quotes is rejected as illiquid
# --------------------------------------------------------------------------- #


def test_confirm_strike_with_no_quotes_is_rejected_as_illiquid() -> None:
    # The analysis agent surfaced only the 145 put; the plan reaches for a 130.
    ctx = _context(candidates=(_candidate(strike=145.0),))
    reaching = _hypothesis(legs=(_leg(strike=130.0),))

    outcome = check_liquidity(reaching, ctx)

    assert outcome.violated is True
    assert outcome.code is ViolationCode.ILLIQUID_CONTRACT
    assert "no quotes" in outcome.detail.lower()
    # buying power on the same plan is fine — the rejection is specific.
    assert check_buying_power(reaching, ctx).passed is True
