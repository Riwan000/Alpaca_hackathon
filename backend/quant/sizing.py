"""Position sizing from a cash budget and contract parameters (P2-BE-14).

The fundamental sizing formula is::

    contracts = floor(budget / (premium * multiplier))

This tells you the largest whole number of option contracts you can buy without
exceeding ``budget`` dollars, where ``premium`` is the per-share option price and
``multiplier`` is the shares-per-contract (100 for a standard US listed option).

Key invariants enforced throughout:
- **Never negative** — a very expensive option or a zero budget → 0 contracts.
- **Zero budget** → 0 contracts (no cash, no trade).
- ``premium`` and ``multiplier`` must be positive; a zero premium is rejected
  because it would imply infinite contracts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.quant.portfolio.position import OPTION_CONTRACT_MULTIPLIER

__all__ = [
    "SizingResult",
    "contracts_from_budget",
    "size_position",
]


def contracts_from_budget(
    budget: float,
    premium: float,
    multiplier: float = OPTION_CONTRACT_MULTIPLIER,
) -> int:
    """Return the maximum whole contracts purchasable within *budget*.

    ``contracts = floor(budget / (premium * multiplier))``

    Parameters
    ----------
    budget:
        Cash available for the hedge leg (must be ``>= 0``).
    premium:
        Option price quoted per share (must be ``> 0``).
    multiplier:
        Shares represented by one contract (must be ``> 0``; default 100).

    Returns
    -------
    int
        Number of contracts ``>= 0``.  A zero budget always returns 0.
    """
    if budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget!r}")
    if premium <= 0:
        raise ValueError(f"premium must be positive, got {premium!r}")
    if multiplier <= 0:
        raise ValueError(f"multiplier must be positive, got {multiplier!r}")

    if budget == 0.0:
        return 0

    raw = budget / (premium * multiplier)
    return max(0, math.floor(raw))


@dataclass(frozen=True)
class SizingResult:
    """Outcome of a position sizing calculation."""

    contracts: int
    """Number of contracts to trade (always ``>= 0``)."""

    cash_required: float
    """Actual cash committed: ``contracts * premium * multiplier``."""

    budget: float
    """The input budget this sizing was computed against."""

    @property
    def budget_utilisation(self) -> float:
        """Fraction of the budget consumed (0.0–1.0); 0.0 when budget is 0."""
        if self.budget == 0.0:
            return 0.0
        return self.cash_required / self.budget

    @property
    def budget_residual(self) -> float:
        """Cash left over after sizing: ``budget - cash_required``."""
        return self.budget - self.cash_required


def size_position(
    budget: float,
    premium: float,
    multiplier: float = OPTION_CONTRACT_MULTIPLIER,
) -> SizingResult:
    """Compute full position sizing for a single option leg.

    Parameters
    ----------
    budget:
        Cash budget for this leg (>= 0).
    premium:
        Per-share option premium (> 0).
    multiplier:
        Shares per contract (> 0; default 100).

    Returns
    -------
    SizingResult
        Contracts, cash committed, and budget metadata.
    """
    n = contracts_from_budget(budget, premium, multiplier)
    cash_required = n * premium * multiplier
    return SizingResult(
        contracts=n,
        cash_required=cash_required,
        budget=budget,
    )
