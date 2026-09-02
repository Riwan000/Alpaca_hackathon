"""Portfolio beta vs a benchmark (P2-BE-6).

``β = Cov(asset, benchmark) / Var(benchmark)`` — the sensitivity of an asset's
returns to the benchmark's. A series identical to the benchmark has ``β = 1``;
a series uncorrelated with it has ``β ≈ 0``; a series that moves opposite it has
a negative β. :func:`portfolio_beta` combines component betas by weight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.quant.risk._stats import covariance, is_constant, variance

__all__ = ["BetaResult", "compute_beta", "beta", "portfolio_beta"]


@dataclass(frozen=True)
class BetaResult:
    """Beta of a series against a benchmark, with its components exposed."""

    beta: float
    covariance: float
    benchmark_variance: float
    observations: int


def compute_beta(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    *,
    ddof: int = 1,
) -> BetaResult:
    """Beta of ``asset_returns`` against ``benchmark_returns`` with a breakdown.

    Raises :class:`ValueError` if the benchmark has zero variance (β undefined)
    or the two series differ in length.
    """
    if is_constant(benchmark_returns):
        raise ValueError("benchmark has zero variance; beta is undefined")
    benchmark_var = variance(benchmark_returns, ddof=ddof)
    cov = covariance(asset_returns, benchmark_returns, ddof=ddof)
    return BetaResult(
        beta=cov / benchmark_var,
        covariance=cov,
        benchmark_variance=benchmark_var,
        observations=len(benchmark_returns),
    )


def beta(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    *,
    ddof: int = 1,
) -> float:
    """``Cov(asset, benchmark) / Var(benchmark)``."""
    return compute_beta(asset_returns, benchmark_returns, ddof=ddof).beta


def portfolio_beta(
    component_returns: Mapping[str, Sequence[float]],
    weights: Mapping[str, float],
    benchmark_returns: Sequence[float],
    *,
    ddof: int = 1,
) -> float:
    """Weight-combined beta: ``Σ wᵢ · βᵢ`` over the weighted components.

    Every symbol in ``weights`` must have a return series in
    ``component_returns``. Weights need not sum to ``1``.
    """
    if not weights:
        raise ValueError("weights is empty")
    total = 0.0
    for symbol, weight in weights.items():
        if symbol not in component_returns:
            raise ValueError(f"no return series for {symbol!r}")
        total += weight * beta(
            component_returns[symbol], benchmark_returns, ddof=ddof
        )
    return total
