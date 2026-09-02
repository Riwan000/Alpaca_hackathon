"""Portfolio volatility — return-series σ and covariance-based σ (P2-BE-5).

Two entry points:

* :func:`volatility` — the standard deviation of a single return series,
  reported both per-period and annualised (``σ · √periods_per_year``).
* :func:`portfolio_volatility` — ``√(wᵀ Σ w)`` for asset weights ``w`` and a
  return covariance matrix ``Σ`` (build one with :func:`covariance_matrix`).

Stdlib only; ``ddof=1`` throughout for unbiased sample moments. A constant
return series has zero volatility.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.quant.helpers import TRADING_DAYS_PER_YEAR
from backend.quant.risk._stats import covariance, stdev

__all__ = [
    "DEFAULT_PERIODS_PER_YEAR",
    "VolatilityResult",
    "annualize",
    "returns_volatility",
    "volatility",
    "covariance_matrix",
    "portfolio_volatility",
]

#: Backward-compatible alias — the canonical name lives in :mod:`backend.quant.helpers`.
DEFAULT_PERIODS_PER_YEAR: int = TRADING_DAYS_PER_YEAR


@dataclass(frozen=True)
class VolatilityResult:
    """Volatility of a return series, per-period and annualised."""

    periodic: float
    annualized: float
    periods_per_year: int
    observations: int


def annualize(
    periodic: float, periods_per_year: int = DEFAULT_PERIODS_PER_YEAR
) -> float:
    """Scale a per-period σ to annual: ``periodic · √periods_per_year``."""
    if periods_per_year <= 0:
        raise ValueError(
            f"periods_per_year must be positive, got {periods_per_year!r}"
        )
    return periodic * math.sqrt(periods_per_year)


def returns_volatility(returns: Sequence[float], *, ddof: int = 1) -> float:
    """Per-period standard deviation of ``returns`` (``0`` for a flat series)."""
    return stdev(returns, ddof=ddof)


def volatility(
    returns: Sequence[float],
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ddof: int = 1,
) -> VolatilityResult:
    """Full volatility profile of a single return series."""
    periodic = stdev(returns, ddof=ddof)
    return VolatilityResult(
        periodic=periodic,
        annualized=annualize(periodic, periods_per_year),
        periods_per_year=periods_per_year,
        observations=len(returns),
    )


def covariance_matrix(
    returns_by_asset: Mapping[str, Sequence[float]], *, ddof: int = 1
) -> dict[str, dict[str, float]]:
    """Symmetric asset-by-asset return covariance matrix.

    Every series must be the same length; the diagonal is each asset's own
    variance.
    """
    if not returns_by_asset:
        raise ValueError("returns_by_asset is empty")
    assets = list(returns_by_asset)
    matrix: dict[str, dict[str, float]] = {asset: {} for asset in assets}
    for i, row_asset in enumerate(assets):
        for col_asset in assets[i:]:
            cov = covariance(
                returns_by_asset[row_asset],
                returns_by_asset[col_asset],
                ddof=ddof,
            )
            matrix[row_asset][col_asset] = cov
            matrix[col_asset][row_asset] = cov
    return matrix


def portfolio_volatility(
    weights: Mapping[str, float],
    covariance_by_asset: Mapping[str, Mapping[str, float]],
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    annualized: bool = True,
) -> float:
    """``√(wᵀ Σ w)`` — portfolio σ from asset weights and a covariance matrix.

    ``weights`` need not sum to ``1`` (a net-exposure book may sum to less).
    Every weighted asset must have a full covariance row in
    ``covariance_by_asset``.
    """
    if not weights:
        raise ValueError("weights is empty")
    missing = sorted(a for a in weights if a not in covariance_by_asset)
    if missing:
        raise ValueError(f"no covariance row for: {', '.join(missing)}")
    total_variance = 0.0
    for row_asset, weight_row in weights.items():
        row = covariance_by_asset[row_asset]
        for col_asset, weight_col in weights.items():
            if col_asset not in row:
                raise ValueError(
                    f"no covariance entry for ({row_asset!r}, {col_asset!r})"
                )
            total_variance += weight_row * weight_col * row[col_asset]
    periodic = math.sqrt(max(total_variance, 0.0))
    return annualize(periodic, periods_per_year) if annualized else periodic
