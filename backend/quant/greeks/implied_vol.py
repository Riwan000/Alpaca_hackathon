"""Implied-volatility solver for Black-Scholes European options (P2-BE-10).

Given an observed option ``price``, recover the ``volatility`` that makes
:func:`backend.quant.greeks.black_scholes.bs_price` reproduce it.

The model price is continuous and strictly increasing in volatility, from its
discounted-intrinsic floor (as ``sigma -> 0``) up to a no-arbitrage ceiling
(the carry-adjusted spot for a call, the discounted strike for a put). The
solver takes a Newton step when the local slope (``vega``) is well behaved and
falls back to bisection otherwise — the safeguarded "rtsafe" scheme from
*Numerical Recipes*. A price outside the reachable band, or one that fails to
converge within :data:`MAX_ITERATIONS`, raises :class:`ImpliedVolError` rather
than looping forever.
"""

from __future__ import annotations

import math

from backend.quant.greeks.black_scholes import OptionKind, bs_price, to_option_kind, vega

__all__ = [
    "ImpliedVolError",
    "implied_volatility",
    "VOL_BOUNDS",
    "PRICE_TOLERANCE",
    "VOL_TOLERANCE",
    "MAX_ITERATIONS",
]

#: ``(low, high)`` annualised-volatility bracket the solver searches within.
VOL_BOUNDS: tuple[float, float] = (1e-6, 5.0)
#: Absolute convergence tolerance on the option price.
PRICE_TOLERANCE: float = 1e-8
#: Absolute convergence tolerance on the volatility step.
VOL_TOLERANCE: float = 1e-10
#: Hard iteration cap — guarantees the solver terminates.
MAX_ITERATIONS: int = 100


class ImpliedVolError(ValueError):
    """No implied volatility fits the supplied price (unreachable or non-convergent)."""


def implied_volatility(
    price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    kind: OptionKind | str,
    dividend_yield: float = 0.0,
    *,
    price_tolerance: float = PRICE_TOLERANCE,
    vol_tolerance: float = VOL_TOLERANCE,
    max_iterations: int = MAX_ITERATIONS,
    vol_bounds: tuple[float, float] = VOL_BOUNDS,
) -> float:
    """Solve ``bs_price(volatility) == price`` for ``volatility``.

    Raises :class:`ImpliedVolError` if ``price`` is not finite, sits at or
    outside the model's no-arbitrage band, or the search does not converge in
    ``max_iterations``. :class:`ImpliedVolError` is a :class:`ValueError`.
    """
    option = to_option_kind(kind)
    low, high = vol_bounds
    if not math.isfinite(price):
        raise ImpliedVolError(f"price must be finite, got {price!r}")
    if not (0.0 < low < high):
        raise ValueError(f"vol_bounds must satisfy 0 < low < high, got {vol_bounds!r}")
    if price_tolerance <= 0 or vol_tolerance <= 0:
        raise ValueError("price_tolerance and vol_tolerance must be positive")
    if max_iterations <= 0:
        raise ValueError(f"max_iterations must be positive, got {max_iterations!r}")

    def excess(volatility: float) -> float:
        return (
            bs_price(spot, strike, time_to_expiry, volatility, rate, option, dividend_yield)
            - price
        )

    excess_low = excess(low)
    excess_high = excess(high)
    if excess_low > 0.0:
        raise ImpliedVolError(
            f"price {price!r} is below the model's minimum "
            f"{price + excess_low!r}; no positive implied volatility exists"
        )
    if excess_high < 0.0:
        raise ImpliedVolError(
            f"price {price!r} implies a volatility above {high!r}"
        )
    if -excess_low <= price_tolerance:
        return low
    if excess_high <= price_tolerance:
        return high

    # Safeguarded Newton: keep a bracket [low, high] with excess(low) < 0 < excess(high)
    # and prefer a Newton step, bisecting whenever it lands outside the bracket
    # or the slope has collapsed.
    volatility = 0.5 * (low + high)
    step = high - low
    step_prev = step
    value = excess(volatility)
    slope = vega(spot, strike, time_to_expiry, volatility, rate, dividend_yield)
    for _ in range(max_iterations):
        newton_out_of_range = ((volatility - high) * slope - value) * (
            (volatility - low) * slope - value
        ) > 0.0
        newton_too_slow = abs(2.0 * value) > abs(step_prev * slope)
        step_prev = step
        if slope <= 0.0 or newton_out_of_range or newton_too_slow:
            step = 0.5 * (high - low)
            volatility = low + step
        else:
            step = value / slope
            volatility = volatility - step
        if abs(step) <= vol_tolerance:
            return volatility
        value = excess(volatility)
        slope = vega(spot, strike, time_to_expiry, volatility, rate, dividend_yield)
        if abs(value) <= price_tolerance:
            return volatility
        if value < 0.0:
            low = volatility
        else:
            high = volatility
    raise ImpliedVolError(
        f"implied volatility did not converge within {max_iterations} iterations"
    )
