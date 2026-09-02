"""The position primitive the portfolio quant functions operate on — Phase 2.

Deliberately decoupled from :class:`backend.models.common.PortfolioPosition`
(the pydantic wire contract): the quant layer is pure and must not import the
agent-state models. Map a wire position onto :class:`Position` at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Position", "signed_notional", "gross_notional"]

#: Notional multiplier for a plain equity share.
EQUITY_MULTIPLIER: float = 1.0
#: Notional multiplier for a standard US listed option contract.
OPTION_CONTRACT_MULTIPLIER: float = 100.0


@dataclass(frozen=True)
class Position:
    """A single held position as the quant engine sees it.

    ``quantity`` is **signed** — a short position carries a negative quantity.
    ``price`` is the current mark per unit (non-negative). ``multiplier`` scales
    one unit to its notional: ``1`` for equity, ``100`` for a standard option
    contract.
    """

    symbol: str
    quantity: float
    price: float
    multiplier: float = EQUITY_MULTIPLIER

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError(
                f"{self.symbol}: price must be non-negative, got {self.price!r}"
            )
        if self.multiplier <= 0:
            raise ValueError(
                f"{self.symbol}: multiplier must be positive, got {self.multiplier!r}"
            )


def signed_notional(position: Position) -> float:
    """``quantity · price · multiplier`` — negative for a short position."""
    return position.quantity * position.price * position.multiplier


def gross_notional(position: Position) -> float:
    """Absolute notional of a position (always ``>= 0``)."""
    return abs(signed_notional(position))
