"""Portfolio concentration — HHI and top-N weight (P2-BE-3).

Weights are taken by **absolute notional** and aggregated per symbol, so a short
counts toward concentration at its gross size. The Herfindahl-Hirschman Index is
``Σ wᵢ²``: ``1.0`` for a single holding, ``1/N`` for N equal holdings, trending
to ``0`` as the book diversifies. ``1 / HHI`` is the effective number of
equal-weight holdings. The CRₙ concentration ratio is the combined weight of the
``n`` largest holdings.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from backend.quant.portfolio.position import Position, gross_notional

__all__ = [
    "Concentration",
    "weights",
    "hhi",
    "effective_holdings",
    "top_n_weight",
    "compute_concentration",
]

#: Concentration ratios reported by :func:`compute_concentration` by default.
DEFAULT_TOP_NS: tuple[int, ...] = (1, 3, 5)


def weights(positions: Iterable[Position]) -> dict[str, float]:
    """Per-symbol portfolio weight by absolute notional (sums to ``1.0``).

    An empty book, or one whose notionals net to zero, yields ``{}``.
    """
    notionals: dict[str, float] = {}
    for position in positions:
        notionals[position.symbol] = (
            notionals.get(position.symbol, 0.0) + gross_notional(position)
        )
    total = sum(notionals.values())
    if total <= 0:
        return {}
    return {symbol: notional / total for symbol, notional in notionals.items()}


def hhi(positions: Iterable[Position]) -> float:
    """Herfindahl-Hirschman Index ``Σ wᵢ²``. Empty book → ``0.0``."""
    return sum(weight * weight for weight in weights(positions).values())


def effective_holdings(positions: Iterable[Position]) -> float:
    """``1 / HHI`` — equivalent count of equal-weight holdings. Empty → ``0.0``."""
    index = hhi(positions)
    return 1.0 / index if index > 0 else 0.0


def top_n_weight(positions: Iterable[Position], n: int) -> float:
    """Combined weight of the ``n`` largest holdings (the CRₙ ratio)."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")
    ranked = sorted(weights(positions).values(), reverse=True)
    return sum(ranked[:n])


@dataclass(frozen=True)
class Concentration:
    """Concentration profile of a book.

    ``weights`` is ``(symbol, weight)`` pairs in descending order; ``top_n`` is
    ``(n, combined weight)`` pairs for each requested ``n``.
    """

    weights: tuple[tuple[str, float], ...]
    hhi: float
    effective_holdings: float
    top_n: tuple[tuple[int, float], ...]


def compute_concentration(
    positions: Iterable[Position],
    top_ns: Sequence[int] = DEFAULT_TOP_NS,
) -> Concentration:
    """Aggregate ``positions`` into a :class:`Concentration` profile."""
    ranked = sorted(
        weights(positions).items(), key=lambda item: item[1], reverse=True
    )
    ranked_weights = [weight for _, weight in ranked]
    index = sum(weight * weight for weight in ranked_weights)
    return Concentration(
        weights=tuple(ranked),
        hhi=index,
        effective_holdings=1.0 / index if index > 0 else 0.0,
        top_n=tuple((n, sum(ranked_weights[:n])) for n in top_ns),
    )
