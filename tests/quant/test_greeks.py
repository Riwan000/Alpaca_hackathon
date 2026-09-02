"""Unit tests for Black-Scholes price and greeks — tasks P2-BE-9, P2-BE-19.

Reference case: an ATM 1-year option, ``S = K = 100``, ``r = 5%``,
``sigma = 20%``, ``q = 0``. Reference numbers cross-checked against Hull,
*Options, Futures, and Other Derivatives* (vega quoted per 1.00 of vol,
theta per year).
"""

from __future__ import annotations

import math

import pytest

from backend.quant.greeks.black_scholes import (
    DAYS_PER_YEAR,
    OptionKind,
    black_scholes,
    bs_price,
    delta,
    gamma,
    theta,
    vega,
)

pytestmark = pytest.mark.unit

SPOT = 100.0
STRIKE = 100.0
TIME = 1.0
RATE = 0.05
VOL = 0.20

CALL_PRICE = 10.4506
PUT_PRICE = 5.5735
CALL_DELTA = 0.6368
PUT_DELTA = -0.3632
GAMMA = 0.018762
VEGA = 37.524
CALL_THETA = -6.4140
PUT_THETA = -1.6579
#: A per-day theta would be ~1/365 of the annual figure; stay well above that.
ANNUAL_THETA_FLOOR = 1.0


def test_atm_call_price_matches_reference() -> None:
    price = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)
    assert price == pytest.approx(CALL_PRICE, abs=2e-3)


def test_atm_put_price_matches_reference() -> None:
    price = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT)
    assert price == pytest.approx(PUT_PRICE, abs=2e-3)


def test_call_greeks_match_reference() -> None:
    g = black_scholes(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)

    assert g.price == pytest.approx(CALL_PRICE, abs=2e-3)
    assert g.delta == pytest.approx(CALL_DELTA, abs=2e-3)
    assert g.gamma == pytest.approx(GAMMA, abs=5e-5)
    assert g.vega == pytest.approx(VEGA, abs=3e-2)
    assert g.theta == pytest.approx(CALL_THETA, abs=3e-3)


def test_put_greeks_match_reference() -> None:
    g = black_scholes(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT)

    assert g.price == pytest.approx(PUT_PRICE, abs=2e-3)
    assert g.delta == pytest.approx(PUT_DELTA, abs=2e-3)
    assert g.gamma == pytest.approx(GAMMA, abs=5e-5)  # gamma is kind-independent
    assert g.vega == pytest.approx(VEGA, abs=3e-2)  # vega is kind-independent
    assert g.theta == pytest.approx(PUT_THETA, abs=3e-3)


def test_put_call_parity_holds() -> None:
    call = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)
    put = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT)

    # C - P == S - K * e^{-rT}   (with q = 0)
    assert call - put == pytest.approx(SPOT - STRIKE * math.exp(-RATE * TIME), abs=1e-9)


def test_gamma_and_vega_are_identical_for_call_and_put() -> None:
    call = black_scholes(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)
    put = black_scholes(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT)

    assert call.gamma == pytest.approx(put.gamma)
    assert call.vega == pytest.approx(put.vega)
    assert gamma(SPOT, STRIKE, TIME, VOL, RATE) == pytest.approx(call.gamma)
    assert vega(SPOT, STRIKE, TIME, VOL, RATE) == pytest.approx(call.vega)


def test_delta_stays_within_bounds_across_moneyness() -> None:
    deep_itm_call = delta(1_000.0, STRIKE, TIME, VOL, RATE, OptionKind.CALL)
    deep_otm_call = delta(1.0, STRIKE, TIME, VOL, RATE, OptionKind.CALL)

    assert deep_itm_call == pytest.approx(1.0, abs=1e-6)
    assert deep_otm_call == pytest.approx(0.0, abs=1e-6)
    assert -1.0 < delta(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT) < 0.0


def test_theta_reference_is_annual_not_daily() -> None:
    annual = theta(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)

    assert annual == pytest.approx(CALL_THETA, abs=3e-3)
    # a per-day convention would be ~1/365 of this — guard against that mix-up
    assert abs(annual) > ANNUAL_THETA_FLOOR


def test_dividend_yield_lowers_a_call_and_lifts_a_put() -> None:
    call_no_div = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)
    call_with_div = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL, dividend_yield=0.03)
    put_no_div = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT)
    put_with_div = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.PUT, dividend_yield=0.03)

    assert call_with_div < call_no_div
    assert put_with_div > put_no_div


def test_kind_accepts_case_insensitive_strings() -> None:
    from_enum = bs_price(SPOT, STRIKE, TIME, VOL, RATE, OptionKind.CALL)

    assert bs_price(SPOT, STRIKE, TIME, VOL, RATE, "call") == pytest.approx(from_enum)
    assert bs_price(SPOT, STRIKE, TIME, VOL, RATE, "Call") == pytest.approx(from_enum)


def test_invalid_kind_raises() -> None:
    with pytest.raises(ValueError):
        bs_price(SPOT, STRIKE, TIME, VOL, RATE, "straddle")


@pytest.mark.parametrize(
    ("spot", "strike", "time_to_expiry", "volatility"),
    [
        (0.0, STRIKE, TIME, VOL),
        (-1.0, STRIKE, TIME, VOL),
        (SPOT, 0.0, TIME, VOL),
        (SPOT, STRIKE, 0.0, VOL),
        (SPOT, STRIKE, -0.5, VOL),
        (SPOT, STRIKE, TIME, 0.0),
        (SPOT, STRIKE, TIME, -0.2),
    ],
)
def test_non_positive_inputs_are_rejected(
    spot: float, strike: float, time_to_expiry: float, volatility: float
) -> None:
    with pytest.raises(ValueError):
        bs_price(spot, strike, time_to_expiry, volatility, RATE, OptionKind.CALL)


def test_days_per_year_constant_is_exposed() -> None:
    assert DAYS_PER_YEAR == 365.0
