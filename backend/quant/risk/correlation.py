"""Pairwise and matrix correlation (P2-BE-7).

Pearson correlation ``ρ = Cov(x, y) / (σx · σy)``, bounded to ``[-1, 1]``. A
series correlated with itself gives ``1``; a series against its own negation
gives ``-1``. :func:`correlation_matrix` is symmetric with a unit diagonal.
A constant series has no defined correlation and raises :class:`ValueError`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.quant.risk._stats import covariance, is_constant, stdev

__all__ = ["CorrelationMatrix", "correlation", "correlation_matrix"]


def _clamp_unit(value: float) -> float:
    """Pull a rounding-error overshoot back into ``[-1, 1]``."""
    return max(-1.0, min(1.0, value))


def correlation(
    xs: Sequence[float], ys: Sequence[float], *, ddof: int = 1
) -> float:
    """Pearson correlation of ``xs`` and ``ys``, clamped to ``[-1, 1]``."""
    if is_constant(xs) or is_constant(ys):
        raise ValueError("cannot correlate a constant series")
    std_x = stdev(xs, ddof=ddof)
    std_y = stdev(ys, ddof=ddof)
    return _clamp_unit(covariance(xs, ys, ddof=ddof) / (std_x * std_y))


@dataclass(frozen=True)
class CorrelationMatrix:
    """Square correlation matrix over named series.

    ``names`` preserves input order; ``rows`` maps each name to its correlation
    against every name (symmetric, unit diagonal).
    """

    names: tuple[str, ...]
    rows: dict[str, dict[str, float]]

    def get(self, a: str, b: str) -> float:
        """Correlation between series ``a`` and series ``b``."""
        return self.rows[a][b]


def correlation_matrix(
    series_by_name: Mapping[str, Sequence[float]], *, ddof: int = 1
) -> CorrelationMatrix:
    """Symmetric name-by-name correlation matrix with a unit diagonal."""
    if not series_by_name:
        raise ValueError("series_by_name is empty")
    names = list(series_by_name)
    constant = sorted(n for n in names if is_constant(series_by_name[n]))
    if constant:
        raise ValueError(f"cannot correlate a constant series: {', '.join(constant)}")
    rows: dict[str, dict[str, float]] = {name: {} for name in names}
    for i, row_name in enumerate(names):
        rows[row_name][row_name] = 1.0
        for col_name in names[i + 1 :]:
            rho = correlation(
                series_by_name[row_name], series_by_name[col_name], ddof=ddof
            )
            rows[row_name][col_name] = rho
            rows[col_name][row_name] = rho
    return CorrelationMatrix(names=tuple(names), rows=rows)
