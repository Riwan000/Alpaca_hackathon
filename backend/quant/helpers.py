"""Shared numeric helpers for the quant engine (P2-BE-16).

All annualization factors and return calculations live here so that the rest of
the ``quant/`` layer never embeds a bare ``252`` or ``365`` literal.

Constants
---------
:data:`TRADING_DAYS_PER_YEAR`
    The conventional equity-market trading-day count (252).  Used whenever a
    per-day return series is scaled to an annualised figure.

:data:`CALENDAR_DAYS_PER_YEAR`
    Calendar days per year (365.0).  Used for time-based option pricing
    (e.g. converting Black-Scholes annualised theta to a per-day figure).

:data:`WEEKS_PER_YEAR`
    ISO weeks per year (52).  Useful for weekly return series.

:data:`MONTHS_PER_YEAR`
    Months per year (12).  Useful for monthly return series.

Return helpers
--------------
:func:`returns_from_prices`
    Simple (percentage) returns from a price series.

:func:`log_returns_from_prices`
    Log (continuously compounded) returns from a price series.

Annualization helpers
---------------------
:func:`annualize_factor`
    ``sqrt(periods_per_year)`` — multiply a per-period σ by this to get annual σ.

:func:`annualize`
    ``periodic_value * sqrt(periods_per_year)``.

:func:`deannualize`
    Inverse: convert an annualised σ back to per-period.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    # Named constants
    "TRADING_DAYS_PER_YEAR",
    "CALENDAR_DAYS_PER_YEAR",
    "WEEKS_PER_YEAR",
    "MONTHS_PER_YEAR",
    # Return helpers
    "returns_from_prices",
    "log_returns_from_prices",
    # Annualization helpers
    "annualize_factor",
    "annualize",
    "deannualize",
]

# ---------------------------------------------------------------------------
# Named constants — no magic numbers anywhere else in quant/
# ---------------------------------------------------------------------------

#: Conventional equity-market trading days per year (used for daily → annual σ).
TRADING_DAYS_PER_YEAR: int = 252

#: Calendar days per year (used in option time-value / theta calculations).
CALENDAR_DAYS_PER_YEAR: float = 365.0

#: ISO weeks per year (used for weekly return series).
WEEKS_PER_YEAR: int = 52

#: Months per year (used for monthly return series).
MONTHS_PER_YEAR: int = 12


# ---------------------------------------------------------------------------
# Return calculation helpers
# ---------------------------------------------------------------------------


def returns_from_prices(prices: Sequence[float]) -> list[float]:
    """Compute simple (percentage) returns from a price series.

    ``r_t = (P_t - P_{t-1}) / P_{t-1}``

    Parameters
    ----------
    prices:
        Time-ordered price series (must have at least 2 elements; every price
        must be strictly positive).

    Returns
    -------
    list[float]
        Return series of length ``len(prices) - 1``.  Positive means
        appreciation, negative means decline.

    Raises
    ------
    ValueError
        If ``prices`` has fewer than 2 elements, or any price is ``<= 0``.

    Examples
    --------
    >>> returns_from_prices([100.0, 110.0, 99.0])
    [0.1, -0.1]
    """
    if len(prices) < 2:
        raise ValueError(
            f"prices must have at least 2 elements, got {len(prices)}"
        )
    for i, p in enumerate(prices):
        if p <= 0:
            raise ValueError(
                f"prices[{i}] must be positive, got {p!r}"
            )
    return [
        (prices[i] - prices[i - 1]) / prices[i - 1]
        for i in range(1, len(prices))
    ]


def log_returns_from_prices(prices: Sequence[float]) -> list[float]:
    """Compute log (continuously compounded) returns from a price series.

    ``r_t = ln(P_t / P_{t-1})``

    Parameters
    ----------
    prices:
        Time-ordered price series (at least 2 elements; every price must be
        strictly positive).

    Returns
    -------
    list[float]
        Log-return series of length ``len(prices) - 1``.

    Raises
    ------
    ValueError
        If ``prices`` has fewer than 2 elements, or any price is ``<= 0``.

    Examples
    --------
    >>> import math
    >>> log_returns_from_prices([100.0, math.e * 100])  # one e-fold → ln = 1
    [1.0]
    """
    if len(prices) < 2:
        raise ValueError(
            f"prices must have at least 2 elements, got {len(prices)}"
        )
    for i, p in enumerate(prices):
        if p <= 0:
            raise ValueError(
                f"prices[{i}] must be positive, got {p!r}"
            )
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]


# ---------------------------------------------------------------------------
# Annualization helpers
# ---------------------------------------------------------------------------


def annualize_factor(periods_per_year: int | float) -> float:
    """``sqrt(periods_per_year)`` — the multiplier that scales a per-period σ
    to an annualised σ.

    Parameters
    ----------
    periods_per_year:
        Number of return periods in a year (e.g. :data:`TRADING_DAYS_PER_YEAR`
        for daily returns, :data:`WEEKS_PER_YEAR` for weekly).  Must be
        ``> 0``.

    Returns
    -------
    float
        ``sqrt(periods_per_year)``.

    Raises
    ------
    ValueError
        If ``periods_per_year <= 0``.
    """
    if periods_per_year <= 0:
        raise ValueError(
            f"periods_per_year must be positive, got {periods_per_year!r}"
        )
    return math.sqrt(periods_per_year)


def annualize(
    periodic_value: float,
    periods_per_year: int | float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Scale a per-period volatility to annual: ``periodic_value * sqrt(periods_per_year)``.

    Parameters
    ----------
    periodic_value:
        Per-period σ (or any quantity that scales with ``sqrt(time)``).
    periods_per_year:
        Number of return periods in a year.  Defaults to
        :data:`TRADING_DAYS_PER_YEAR` (252).

    Returns
    -------
    float
        Annualised value.
    """
    return periodic_value * annualize_factor(periods_per_year)


def deannualize(
    annual_value: float,
    periods_per_year: int | float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Convert an annualised σ back to per-period: ``annual_value / sqrt(periods_per_year)``.

    Parameters
    ----------
    annual_value:
        Annualised σ (or any quantity that scales with ``sqrt(time)``).
    periods_per_year:
        Number of return periods in a year.  Defaults to
        :data:`TRADING_DAYS_PER_YEAR` (252).

    Returns
    -------
    float
        Per-period value.
    """
    return annual_value / annualize_factor(periods_per_year)
