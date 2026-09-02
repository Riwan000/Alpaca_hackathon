"""Option pricing greeks — Phase 2 (tasks P2-BE-9, P2-BE-10).

Pure Black-Scholes-Merton: price, delta, gamma, vega and theta, plus an
implied-volatility solver. No LLM, no I/O, no NumPy/SciPy.
"""

from __future__ import annotations

from backend.quant.greeks.black_scholes import (
    DAYS_PER_YEAR,
    Greeks,
    OptionKind,
    black_scholes,
    bs_price,
    d1_d2,
    delta,
    gamma,
    theta,
    to_option_kind,
    vega,
)
from backend.quant.greeks.implied_vol import (
    MAX_ITERATIONS,
    PRICE_TOLERANCE,
    VOL_BOUNDS,
    VOL_TOLERANCE,
    ImpliedVolError,
    implied_volatility,
)

__all__ = [
    # black-scholes
    "OptionKind",
    "Greeks",
    "DAYS_PER_YEAR",
    "to_option_kind",
    "d1_d2",
    "bs_price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "black_scholes",
    # implied vol
    "ImpliedVolError",
    "implied_volatility",
    "VOL_BOUNDS",
    "PRICE_TOLERANCE",
    "VOL_TOLERANCE",
    "MAX_ITERATIONS",
]
