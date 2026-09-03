"""Deterministic risk engine — execution-tolerance / price-band screen — P5-BE-6.

A hard gate beside the P5-BE-1/2 limits (BRD §19): a leg whose limit price
strays past the allowed percentage band around the contract mid is rejected —
it either overpays into a stale quote or will never fill. Only legs that carry
a ``limit_price`` are screened; exactly on the band edge passes.

The confirm scenario rejects a plan priced 20 % off mid.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.agents.risk import (
    DEFAULT_MAX_PRICE_DEVIATION_PCT,
    ViolationCode,
    check_price_band,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-6"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = date(2026, 10, 3)
_STRIKE = 145.0
# bid 3.5 / ask 4.5 → mid 4.0, exact in binary floating point.
_MID = 4.0


def _context(*, bid: float | None = 3.5, ask: float | None = 4.5) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [],
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": [
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "strike": _STRIKE,
                    "expiration": _EXPIRY.isoformat(),
                    "premium": 4.0,
                    "bid": bid,
                    "ask": ask,
                    "open_interest": 4200,
                }
            ],
        }
    )


def _leg(*, limit_price: float | None, strike: float = _STRIKE) -> OptionLeg:
    return OptionLeg(
        underlying="AAPL",
        right=OptionRight.PUT,
        side=OrderSide.BUY,
        strike=strike,
        expiration=_EXPIRY,
        quantity=1,
        limit_price=limit_price,
    )


def _hypothesis(*, legs: tuple[OptionLeg, ...]) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=_CYCLE,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=400.0,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5),
        rationale="synthetic hypothesis for the P5-BE-6 screen",
    )


def test_default_price_band_is_five_percent() -> None:
    assert DEFAULT_MAX_PRICE_DEVIATION_PCT == 0.05


def test_limit_price_inside_the_band_passes() -> None:
    outcome = check_price_band(_hypothesis(legs=(_leg(limit_price=4.08),)), _context())

    assert outcome.passed is True
    assert outcome.code is None


def test_limit_price_far_off_mid_fails() -> None:
    # 4.8 is 20% above mid 4.0.
    outcome = check_price_band(_hypothesis(legs=(_leg(limit_price=4.8),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.PRICE_BAND_EXCEEDED
    assert outcome.observed == pytest.approx(0.20)
    assert outcome.limit == pytest.approx(0.05)


def test_limit_price_well_below_mid_fails() -> None:
    outcome = check_price_band(_hypothesis(legs=(_leg(limit_price=3.2),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.PRICE_BAND_EXCEEDED
    assert outcome.observed == pytest.approx(0.20)


def test_limit_price_exactly_on_the_band_edge_passes() -> None:
    # override band to 25% and price at mid * 1.25 = 5.0 → deviation exactly 0.25.
    outcome = check_price_band(
        _hypothesis(legs=(_leg(limit_price=5.0),)), _context(), max_deviation_pct=0.25
    )

    assert outcome.passed is True
    assert outcome.code is None


def test_limit_price_just_past_the_edge_fails() -> None:
    outcome = check_price_band(
        _hypothesis(legs=(_leg(limit_price=5.5),)), _context(), max_deviation_pct=0.25
    )

    assert outcome.passed is False
    assert outcome.code is ViolationCode.PRICE_BAND_EXCEEDED


def test_leg_without_a_limit_price_is_not_screened() -> None:
    outcome = check_price_band(_hypothesis(legs=(_leg(limit_price=None),)), _context())

    assert outcome.passed is True
    assert "no limit-priced legs" in outcome.detail


def test_limit_priced_leg_with_no_matching_quote_is_skipped() -> None:
    # limit price set, but the only candidate is a different strike → no mid.
    outcome = check_price_band(
        _hypothesis(legs=(_leg(limit_price=4.8, strike=150.0),)), _context()
    )

    assert outcome.passed is True
    assert "no limit-priced legs" in outcome.detail


def test_first_out_of_band_leg_in_order_is_reported() -> None:
    legs = (_leg(limit_price=4.05), _leg(limit_price=4.8, strike=145.0))
    outcome = check_price_band(_hypothesis(legs=legs), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.PRICE_BAND_EXCEEDED


def test_price_band_outcome_maps_to_the_execution_category() -> None:
    check = check_price_band(
        _hypothesis(legs=(_leg(limit_price=4.0),)), _context()
    ).to_risk_check()

    assert check.category == "EXECUTION"
    assert check.name == "price_band"


# --------------------------------------------------------------------------- #
# Confirm — a plan priced 20% off mid is rejected
# --------------------------------------------------------------------------- #


def test_confirm_plan_priced_twenty_percent_off_mid_is_rejected() -> None:
    ctx = _context()  # mid 4.0
    off_mid = _hypothesis(legs=(_leg(limit_price=_MID * 1.20),))

    outcome = check_price_band(off_mid, ctx)

    assert outcome.violated is True
    assert outcome.code is ViolationCode.PRICE_BAND_EXCEEDED
    assert outcome.observed == pytest.approx(0.20)
    assert outcome.limit == pytest.approx(0.05)
    assert "off mid" in outcome.detail
