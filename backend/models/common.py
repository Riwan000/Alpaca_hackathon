"""Shared building blocks for the agent-state contracts — tasks P1-BE-9..14.

:class:`Contract` is the common base: strict (unknown keys rejected), immutable
(``frozen``), and populated from either attribute or alias. :class:`OptionLeg`
and :class:`PortfolioPosition` are reused across several contracts, so they live
here rather than being redefined per module.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import AssetClass, OptionRight, OrderSide

__all__ = ["Contract", "OptionLeg", "PortfolioPosition"]


class Contract(BaseModel):
    """Base for every agent-state contract.

    - ``extra="forbid"`` — a fixture with an unknown key is rejected, not
      silently dropped. This is what makes the "rejects a bad one" half of the
      round-trip tests meaningful.
    - ``frozen=True`` — instances are immutable and hashable; downstream code
      evolves a contract with :meth:`~pydantic.BaseModel.model_copy`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class OptionLeg(Contract):
    """One option leg of a hedge structure."""

    underlying: str
    right: OptionRight
    side: OrderSide
    strike: float = Field(gt=0)
    expiration: date
    quantity: int = Field(gt=0, description="number of contracts (always positive)")
    limit_price: float | None = Field(default=None, ge=0)
    occ_symbol: str | None = Field(
        default=None, description="full OCC option identifier when resolved"
    )


class PortfolioPosition(Contract):
    """A single held position inside :class:`PortfolioState`."""

    symbol: str
    qty: float
    avg_price: float = Field(ge=0)
    market_value: float
    asset_class: AssetClass = AssetClass.EQUITY
    side: OrderSide = OrderSide.BUY
    unrealized_pl: float | None = None
