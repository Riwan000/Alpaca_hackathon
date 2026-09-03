"""Portfolio Analysis Agent — task P3-BE-5 (BRD §12).

Turns the Portfolio context slice into the ``portfolio_state`` section of the
:class:`~backend.models.hedge_context.HedgeContext`. Every number is recomputed
here from :mod:`backend.quant` over the held positions and (when supplied) the
portfolio equity curve — the LLM is not consulted, so the output is fully
deterministic and hand-checkable:

* ``gross_exposure`` / ``net_exposure`` — :func:`quant.compute_exposure` over the
  signed position notionals;
* ``concentration_hhi`` — :func:`quant.compute_concentration` (Σ wᵢ² by gross
  weight);
* ``drawdown`` (signed, ≤ 0) / ``max_drawdown`` (magnitude, ≥ 0) —
  :func:`quant.compute_drawdown` over ``equity_curve`` when it has ≥ 2 points,
  else the value already on the snapshot;
* ``volatility`` — annualised σ of the equity-curve returns when available, else
  the snapshot value;
* ``beta`` — passed through from the snapshot (needs per-asset return series to
  recompute, which this slice does not carry).
"""

from __future__ import annotations

from datetime import datetime

from openai import OpenAI
from pydantic import Field

from backend.agents.context_builder import AgentContextSlice
from backend.models.common import Contract, PortfolioPosition
from backend.models.enums import OrderSide
from backend.models.hedge_context import CurrentHedge, HedgeObjective, PortfolioState
from backend.quant.helpers import returns_from_prices
from backend.quant.portfolio import (
    Position,
    compute_concentration,
    compute_drawdown,
    compute_exposure,
)
from backend.quant.risk import volatility as _volatility

__all__ = ["PortfolioAgentInput", "analyze_portfolio"]

# drawdown needs 2 points; a sample stdev of the returns needs 2 returns → 3 points.
_MIN_DRAWDOWN_POINTS = 2
_MIN_VOLATILITY_POINTS = 3
_HHI_MAX = 1.0
_HHI_MIN = 0.0


class PortfolioAgentInput(Contract):
    """The Portfolio agent's validated view of its context slice."""

    cycle_id: str
    timestamp: datetime
    objective: HedgeObjective
    portfolio_state: PortfolioState
    current_hedge: CurrentHedge = Field(default_factory=CurrentHedge)
    equity_curve: list[float] = Field(default_factory=list)
    benchmark_returns: list[float] = Field(default_factory=list)


def _signed_notional(position: PortfolioPosition) -> float:
    """Position market value, negative for a short leg regardless of source sign."""
    value = position.market_value
    if position.side == OrderSide.SELL:
        return -abs(value)
    return value


def _to_quant_positions(state: PortfolioState) -> list[Position]:
    # price carries the whole notional, quantity carries the sign: the quant
    # functions only ever use quantity·price·multiplier, so this is exact and
    # needs no division by a possibly-zero share count.
    return [
        Position(symbol=p.symbol, quantity=1.0 if _signed_notional(p) >= 0 else -1.0,
                 price=abs(_signed_notional(p)))
        for p in state.positions
    ]


def _clamp_hhi(value: float) -> float:
    return max(_HHI_MIN, min(_HHI_MAX, value))


def analyze_portfolio(
    ctx: AgentContextSlice,
    *,
    client: OpenAI | None = None,  # noqa: ARG001 - deterministic agent, kept for a uniform call site
) -> PortfolioState:
    """Return the recomputed ``portfolio_state`` for ``ctx`` (BRD §12)."""
    data = PortfolioAgentInput.model_validate(dict(ctx.payload))
    state = data.portfolio_state
    quant_positions = _to_quant_positions(state)

    exposure = compute_exposure(quant_positions)
    concentration = compute_concentration(quant_positions)

    updates: dict[str, float | None] = {
        "gross_exposure": exposure.gross_exposure,
        "net_exposure": exposure.net_exposure,
        "concentration_hhi": _clamp_hhi(concentration.hhi) if state.positions else None,
    }

    curve = data.equity_curve
    if len(curve) >= _MIN_DRAWDOWN_POINTS:
        dd = compute_drawdown(curve)
        updates["drawdown"] = dd.current_drawdown
        updates["max_drawdown"] = dd.max_drawdown
    # returns_from_prices needs a strictly positive series and a sample stdev of
    # its returns needs ≥ 2 of them; short of that, keep the snapshot volatility.
    if len(curve) >= _MIN_VOLATILITY_POINTS and all(point > 0 for point in curve):
        updates["volatility"] = _volatility(returns_from_prices(curve)).annualized

    return state.model_copy(update=updates)
