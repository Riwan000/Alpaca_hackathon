"""Portfolio value — cash plus the net market value of all positions (P2-BE-1).

Pure aggregation, no I/O. A short position subtracts from the total; an empty
book is worth its cash.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.quant.portfolio.position import Position, signed_notional

__all__ = [
    "PortfolioValue",
    "compute_portfolio_value",
    "portfolio_value",
    "positions_value",
]


@dataclass(frozen=True)
class PortfolioValue:
    """Breakdown of a portfolio's mark-to-market value.

    ``short_value`` is ``<= 0``; ``positions_value`` is the net
    (``long_value + short_value``); ``total_value`` adds ``cash``.
    """

    cash: float
    long_value: float
    short_value: float
    positions_value: float
    total_value: float


def positions_value(positions: Iterable[Position]) -> float:
    """Net market value of ``positions`` (shorts subtract)."""
    return sum(signed_notional(p) for p in positions)


def compute_portfolio_value(
    cash: float, positions: Iterable[Position]
) -> PortfolioValue:
    """Aggregate ``cash`` and ``positions`` into a :class:`PortfolioValue`."""
    long_value = 0.0
    short_value = 0.0
    for position in positions:
        notional = signed_notional(position)
        if notional >= 0:
            long_value += notional
        else:
            short_value += notional
    net = long_value + short_value
    return PortfolioValue(
        cash=cash,
        long_value=long_value,
        short_value=short_value,
        positions_value=net,
        total_value=cash + net,
    )


def portfolio_value(cash: float, positions: Iterable[Position]) -> float:
    """Total portfolio value: ``cash`` + net position value."""
    return compute_portfolio_value(cash, positions).total_value
