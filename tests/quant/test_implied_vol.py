"""Unit tests for the implied-volatility solver — tasks P2-BE-10, P2-BE-20.

price -> IV -> price round-trips within tolerance across the moneyness /
maturity / vol grid; an unreachable or malformed price raises instead of
looping (P2-BE-20: convergence + deep ITM/OTM + edge cases).
"""

from __future__ import annotations

import time

import pytest

from backend.quant.greeks.black_scholes import OptionKind, bs_price
from backend.quant.greeks.implied_vol import ImpliedVolError, implied_volatility

pytestmark = pytest.mark.unit

SPOT = 100.0
RATE = 0.03


@pytest.mark.parametrize("kind", [OptionKind.CALL, OptionKind.PUT])
@pytest.mark.parametrize("moneyness", [0.80, 0.95, 1.00, 1.05, 1.25])
@pytest.mark.parametrize("time_to_expiry", [0.05, 0.5, 2.0])
@pytest.mark.parametrize("true_vol", [0.10, 0.25, 0.60, 1.50])
def test_price_recovers_to_the_same_price(
    kind: OptionKind, moneyness: float, time_to_expiry: float, true_vol: float
) -> None:
    strike = SPOT * moneyness
    price = bs_price(SPOT, strike, time_to_expiry, true_vol, RATE, kind)

    recovered_vol = implied_volatility(price, SPOT, strike, time_to_expiry, RATE, kind)
    round_trip = bs_price(SPOT, strike, time_to_expiry, recovered_vol, RATE, kind)

    assert round_trip == pytest.approx(price, rel=1e-6, abs=1e-6)


@pytest.mark.parametrize("kind", [OptionKind.CALL, OptionKind.PUT])
@pytest.mark.parametrize("moneyness", [0.95, 1.00, 1.05])
@pytest.mark.parametrize("time_to_expiry", [0.25, 1.0, 2.0])
@pytest.mark.parametrize("true_vol", [0.15, 0.35, 0.80])
def test_volatility_is_recovered_when_well_conditioned(
    kind: OptionKind, moneyness: float, time_to_expiry: float, true_vol: float
) -> None:
    strike = SPOT * moneyness
    price = bs_price(SPOT, strike, time_to_expiry, true_vol, RATE, kind)

    recovered_vol = implied_volatility(price, SPOT, strike, time_to_expiry, RATE, kind)

    assert recovered_vol == pytest.approx(true_vol, abs=1e-6)


def test_dividend_yield_round_trips() -> None:
    price = bs_price(SPOT, SPOT, 1.0, 0.30, RATE, OptionKind.CALL, dividend_yield=0.02)

    recovered_vol = implied_volatility(
        price, SPOT, SPOT, 1.0, RATE, OptionKind.CALL, dividend_yield=0.02
    )

    assert recovered_vol == pytest.approx(0.30, abs=1e-6)


def test_deep_otm_call_round_trips() -> None:
    strike, time_to_expiry, true_vol = 200.0, 0.25, 0.40
    price = bs_price(SPOT, strike, time_to_expiry, true_vol, RATE, OptionKind.CALL)

    recovered_vol = implied_volatility(price, SPOT, strike, time_to_expiry, RATE, OptionKind.CALL)

    assert recovered_vol == pytest.approx(true_vol, abs=1e-6)


def test_deep_itm_call_reprices_without_hanging() -> None:
    # a deep-ITM call is almost pure discounted intrinsic: vega ~ 0, so the vol
    # is not numerically recoverable, but the solver must still terminate and
    # return a vol that reproduces the price (P2-BE-20 edge case).
    strike, time_to_expiry, true_vol = 20.0, 0.25, 0.40
    price = bs_price(SPOT, strike, time_to_expiry, true_vol, RATE, OptionKind.CALL)

    recovered_vol = implied_volatility(price, SPOT, strike, time_to_expiry, RATE, OptionKind.CALL)
    round_trip = bs_price(SPOT, strike, time_to_expiry, recovered_vol, RATE, OptionKind.CALL)

    assert round_trip == pytest.approx(price, rel=1e-6, abs=1e-6)


def test_price_below_discounted_intrinsic_raises() -> None:
    with pytest.raises(ImpliedVolError):
        implied_volatility(0.01, SPOT, 50.0, 1.0, RATE, OptionKind.CALL)


def test_price_at_no_arbitrage_ceiling_raises() -> None:
    # a call is worth at most the (carry-adjusted) spot
    with pytest.raises(ImpliedVolError):
        implied_volatility(SPOT, SPOT, SPOT, 1.0, RATE, OptionKind.CALL)


def test_negative_price_raises() -> None:
    with pytest.raises(ValueError):
        implied_volatility(-1.0, SPOT, SPOT, 1.0, RATE, OptionKind.PUT)


def test_nan_price_raises() -> None:
    with pytest.raises(ValueError):
        implied_volatility(float("nan"), SPOT, SPOT, 1.0, RATE, OptionKind.CALL)


def test_non_convergent_input_raises_promptly_instead_of_hanging() -> None:
    started = time.perf_counter()

    with pytest.raises(ValueError):
        implied_volatility(1e9, SPOT, SPOT, 1.0, RATE, OptionKind.CALL)

    assert time.perf_counter() - started < 2.0


def test_volatility_above_custom_bounds_raises() -> None:
    price = bs_price(SPOT, SPOT, 1.0, 0.90, RATE, OptionKind.CALL)

    with pytest.raises(ImpliedVolError):
        implied_volatility(
            price, SPOT, SPOT, 1.0, RATE, OptionKind.CALL, vol_bounds=(1e-6, 0.5)
        )


def test_invalid_bounds_raise() -> None:
    price = bs_price(SPOT, SPOT, 1.0, 0.20, RATE, OptionKind.CALL)

    with pytest.raises(ValueError):
        implied_volatility(price, SPOT, SPOT, 1.0, RATE, OptionKind.CALL, vol_bounds=(0.5, 0.1))
