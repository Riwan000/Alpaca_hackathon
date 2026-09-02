"""Shared descriptive statistics for the risk metrics (P2-BE-5 … P2-BE-8).

Sample moments over plain float sequences, stdlib only — the risk layer stays
as dependency-free as the rest of :mod:`backend.quant`. ``ddof`` is the delta
degrees of freedom: ``1`` (the default) gives the unbiased **sample** variance,
``0`` the population variance. Beta and correlation are ratios of these moments
so their value is independent of ``ddof``; only an absolute volatility depends
on it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = ["is_constant", "mean", "covariance", "variance", "stdev"]


def is_constant(series: Sequence[float]) -> bool:
    """True when every value is identical — variance is exactly zero.

    An epsilon-free degenerate-input check: a series that only *looks* flat but
    carries a real spread still has a (tiny) legitimate variance.
    """
    if len(series) == 0:
        raise ValueError("series is empty")
    return max(series) == min(series)


def _require_same_length(a: Sequence[float], b: Sequence[float]) -> None:
    if len(a) != len(b):
        raise ValueError(f"series length mismatch: {len(a)} vs {len(b)}")


def _require_sample_size(series: Sequence[float], ddof: int) -> None:
    if len(series) <= ddof:
        raise ValueError(
            f"need more than ddof={ddof} observations, got {len(series)}"
        )


def mean(series: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty series."""
    if len(series) == 0:
        raise ValueError("series is empty")
    return math.fsum(series) / len(series)


def covariance(
    a: Sequence[float], b: Sequence[float], *, ddof: int = 1
) -> float:
    """Sample covariance of two equal-length series."""
    _require_same_length(a, b)
    _require_sample_size(a, ddof)
    mean_a = mean(a)
    mean_b = mean(b)
    total = math.fsum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    return total / (len(a) - ddof)


def variance(series: Sequence[float], *, ddof: int = 1) -> float:
    """Sample variance — ``covariance(series, series)``."""
    return covariance(series, series, ddof=ddof)


def stdev(series: Sequence[float], *, ddof: int = 1) -> float:
    """Sample standard deviation. A constant series has ``stdev == 0``."""
    return math.sqrt(max(variance(series, ddof=ddof), 0.0))
