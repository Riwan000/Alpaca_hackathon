"""Premium and hedge cost, in cash and as a fraction of portfolio value (P2-BE-11).

The cash cost of an option leg is ``premium * contracts * multiplier`` — the
premium is quoted per share and one listed contract covers
:data:`~backend.quant.portfolio.position.OPTION_CONTRACT_MULTIPLIER` shares. As a
budget signal the number the hedge agents actually reason about is that cash cost
over the book's current value, e.g. ``0.018`` (``1.8%``) for a protective put.

:func:`premium_cost` handles a single bought leg; :func:`hedge_cost` nets a
multi-leg structure, where a sold leg is a credit and lowers the total.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.quant.portfolio.position import OPTION_CONTRACT_MULTIPLIER

__all__ = [
    "PremiumCost",
    "premium_cash",
    "cost_fraction",
    "premium_cost",
    "net_premium_cash",
    "hedge_cost",
]

#: One leg of a multi-leg premium: ``(premium, signed_contracts, multiplier)``
#: where ``signed_contracts`` is positive for a bought leg, negative for a sold one.
PremiumLeg = tuple[float, float, float]


def premium_cash(
    premium: float,
    contracts: float,
    multiplier: float = OPTION_CONTRACT_MULTIPLIER,
) -> float:
    """Cash outlay for a leg: ``premium * contracts * multiplier``.

    ``premium`` is per share and must be ``>= 0``; ``contracts`` is a count and
    must be ``>= 0`` (use :func:`net_premium_cash` for a mix of buys and sells);
    ``multiplier`` must be ``> 0``.
    """
    if premium < 0:
        raise ValueError(f"premium must be non-negative, got {premium!r}")
    if contracts < 0:
        raise ValueError(f"contracts must be non-negative, got {contracts!r}")
    if multiplier <= 0:
        raise ValueError(f"multiplier must be positive, got {multiplier!r}")
    return premium * contracts * multiplier


def cost_fraction(cash_cost: float, portfolio_value: float) -> float:
    """``cash_cost / portfolio_value``. ``portfolio_value`` must be ``> 0``.

    ``cash_cost`` is taken as signed — a net credit yields a negative fraction.
    """
    if portfolio_value <= 0:
        raise ValueError(f"portfolio_value must be positive, got {portfolio_value!r}")
    return cash_cost / portfolio_value


@dataclass(frozen=True)
class PremiumCost:
    """A hedge's cost in cash and as a fraction of the book."""

    cash: float
    fraction_of_portfolio: float

    @property
    def pct_of_portfolio(self) -> float:
        """The fraction expressed in percent (``0.018`` -> ``1.8``)."""
        return self.fraction_of_portfolio * 100.0


def premium_cost(
    premium: float,
    contracts: float,
    portfolio_value: float,
    multiplier: float = OPTION_CONTRACT_MULTIPLIER,
) -> PremiumCost:
    """Cash cost and portfolio fraction for a single bought-premium hedge."""
    cash = premium_cash(premium, contracts, multiplier)
    return PremiumCost(
        cash=cash,
        fraction_of_portfolio=cost_fraction(cash, portfolio_value),
    )


def net_premium_cash(legs: Iterable[PremiumLeg]) -> float:
    """Net debit (``> 0``) or credit (``< 0``) across ``legs``.

    Each leg is ``(premium, signed_contracts, multiplier)`` — ``signed_contracts``
    positive for a bought leg, negative for a sold leg. ``premium`` is per share
    and must be ``>= 0``; ``multiplier`` must be ``> 0``.
    """
    total = 0.0
    for premium, contracts, multiplier in legs:
        if premium < 0:
            raise ValueError(f"premium must be non-negative, got {premium!r}")
        if multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {multiplier!r}")
        total += premium * contracts * multiplier
    return total


def hedge_cost(
    legs: Iterable[PremiumLeg],
    portfolio_value: float,
) -> PremiumCost:
    """Net cash cost and portfolio fraction for a multi-leg hedge structure."""
    cash = net_premium_cash(legs)
    return PremiumCost(
        cash=cash,
        fraction_of_portfolio=cost_fraction(cash, portfolio_value),
    )
