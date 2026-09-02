"""Unit tests for the expiration payoff curve — P2-BE-12.

Protective put: a flat ``-premium`` floor below the strike, slope 1 above, and
the whole curve monotonic non-decreasing.
"""

from __future__ import annotations

import pytest

from backend.quant.payoff.curve import (
    LegKind,
    PayoffLeg,
    leg_payoff,
    payoff_curve,
    to_leg_kind,
    total_payoff,
)

pytestmark = pytest.mark.unit

STRIKE = 100.0
PUT_PREMIUM = 5.0
ENTRY_SPOT = 100.0

# One synthetic unit (multiplier 1) so the arithmetic is transparent:
# long the underlying at 100, long a put struck at 100 for 5.
PROTECTIVE_PUT = (
    PayoffLeg(kind=LegKind.UNDERLYING, quantity=1, premium=ENTRY_SPOT, multiplier=1.0),
    PayoffLeg(
        kind=LegKind.PUT, quantity=1, strike=STRIKE, premium=PUT_PREMIUM, multiplier=1.0
    ),
)


def test_protective_put_floor_is_flat_at_minus_premium_below_the_strike() -> None:
    for spot in (10.0, 50.0, 80.0, 99.0):
        assert total_payoff(PROTECTIVE_PUT, spot) == pytest.approx(-PUT_PREMIUM)


def test_protective_put_has_slope_one_above_the_strike() -> None:
    below = total_payoff(PROTECTIVE_PUT, 120.0)
    above = total_payoff(PROTECTIVE_PUT, 130.0)

    assert above - below == pytest.approx(10.0)  # 10 higher spot -> 10 more P&L
    assert total_payoff(PROTECTIVE_PUT, 130.0) == pytest.approx(30.0 - PUT_PREMIUM)


def test_protective_put_curve_is_monotonic_non_decreasing() -> None:
    curve = payoff_curve(PROTECTIVE_PUT, low=50.0, high=150.0, steps=100)

    assert curve[0].spot == pytest.approx(50.0)
    assert curve[-1].spot == pytest.approx(150.0)
    for earlier, later in zip(curve, curve[1:]):
        assert later.pnl >= earlier.pnl - 1e-9


def test_protective_put_breakeven_is_entry_spot_plus_premium() -> None:
    assert total_payoff(PROTECTIVE_PUT, ENTRY_SPOT + PUT_PREMIUM) == pytest.approx(0.0)


def test_long_call_is_flat_below_strike_then_rises() -> None:
    call = (
        PayoffLeg(
            kind=LegKind.CALL, quantity=1, strike=STRIKE, premium=4.0, multiplier=1.0
        ),
    )

    assert total_payoff(call, 80.0) == pytest.approx(-4.0)
    assert total_payoff(call, 100.0) == pytest.approx(-4.0)
    assert total_payoff(call, 110.0) == pytest.approx(6.0)


def test_short_put_is_capped_at_the_premium_above_the_strike() -> None:
    short_put = (
        PayoffLeg(
            kind=LegKind.PUT, quantity=-1, strike=STRIKE, premium=5.0, multiplier=1.0
        ),
    )

    assert total_payoff(short_put, 130.0) == pytest.approx(5.0)  # keeps the premium
    assert total_payoff(short_put, 90.0) == pytest.approx(-5.0)  # 10 loss, 5 premium


def test_standard_contract_multiplier_scales_floor_and_slope() -> None:
    legs = (
        PayoffLeg(
            kind=LegKind.UNDERLYING, quantity=100, premium=ENTRY_SPOT, multiplier=1.0
        ),
        PayoffLeg(
            kind=LegKind.PUT, quantity=1, strike=STRIKE, premium=PUT_PREMIUM
        ),  # multiplier 100
    )

    assert total_payoff(legs, 60.0) == pytest.approx(
        -PUT_PREMIUM * 100
    )  # floor = -net premium
    assert total_payoff(legs, 130.0) - total_payoff(legs, 120.0) == pytest.approx(
        1000.0
    )


def test_total_payoff_of_no_legs_is_zero() -> None:
    assert total_payoff((), 123.0) == 0.0


def test_leg_payoff_rejects_a_negative_spot() -> None:
    with pytest.raises(ValueError):
        leg_payoff(PROTECTIVE_PUT[1], -1.0)


def test_to_leg_kind_is_case_insensitive_and_rejects_junk() -> None:
    assert to_leg_kind("put") is LegKind.PUT
    assert to_leg_kind("Call") is LegKind.CALL
    assert to_leg_kind("underlying") is LegKind.UNDERLYING
    with pytest.raises(ValueError):
        to_leg_kind("spread")


def test_payoff_leg_normalises_a_string_kind() -> None:
    leg = PayoffLeg(kind="put", quantity=1, strike=STRIKE, premium=1.0)
    assert leg.kind is LegKind.PUT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": LegKind.PUT, "quantity": 0, "strike": STRIKE},
        {"kind": LegKind.PUT, "quantity": 1, "strike": STRIKE, "premium": -1.0},
        {"kind": LegKind.PUT, "quantity": 1, "strike": STRIKE, "multiplier": 0.0},
        {"kind": LegKind.CALL, "quantity": 1, "strike": 0.0},
        {"kind": LegKind.CALL, "quantity": 1, "strike": -5.0},
    ],
)
def test_payoff_leg_validates_its_inputs(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        PayoffLeg(**kwargs)


@pytest.mark.parametrize(
    ("low", "high", "steps"),
    [(-1.0, 100.0, 10), (100.0, 100.0, 10), (100.0, 50.0, 10), (0.0, 100.0, 0)],
)
def test_payoff_curve_rejects_a_bad_grid(low: float, high: float, steps: int) -> None:
    with pytest.raises(ValueError):
        payoff_curve(PROTECTIVE_PUT, low=low, high=high, steps=steps)
