"""``HedgeContext`` contract — task P1-BE-9 (BRD §14).

The standardized snapshot every downstream strategy decision reasons from. The
sub-sections mirror the BRD tree: ``portfolio_state``, ``market_state``,
``stock_state``, ``news_context``, ``option_candidates``, ``current_hedge``,
``objective`` and ``timestamp``. Only ``portfolio_state`` and ``objective`` are
required — analysis agents populate the rest, and a failed agent leaves its
section absent with the name recorded in ``degraded_sections`` (BRD §31).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from backend.models.common import Contract, OptionLeg, PortfolioPosition
from backend.models.enums import OptionRight, StrategyType

__all__ = [
    "CurrentHedge",
    "HedgeContext",
    "HedgeObjective",
    "MarketState",
    "NewsItem",
    "OptionCandidate",
    "PortfolioState",
    "StockView",
]


class PortfolioState(Contract):
    """Aggregate portfolio value plus the risk metrics computed in ``quant/``."""

    total_value: float
    cash: float
    equity: float
    buying_power: float
    positions: list[PortfolioPosition] = Field(default_factory=list)
    gross_exposure: float | None = None
    net_exposure: float | None = None
    concentration_hhi: float | None = Field(default=None, ge=0, le=1)
    drawdown: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = Field(default=None, ge=0)
    beta: float | None = None


class MarketState(Contract):
    """Regime / index / volatility environment from the Market Analysis Agent."""

    regime: str | None = None
    index_trend: str | None = None
    vix: float | None = Field(default=None, ge=0)
    as_of: datetime | None = None


class StockView(Contract):
    """Per-holding risk note, momentum and key price levels."""

    symbol: str
    risk_note: str | None = None
    momentum: float | None = None
    key_levels: list[float] = Field(default_factory=list)


class NewsItem(Contract):
    """A normalized, relevance-filtered article or event (BRD §13)."""

    headline: str
    ts: datetime
    symbols: list[str] = Field(default_factory=list)
    source: str | None = None
    sentiment: float | None = Field(default=None, ge=-1, le=1)
    is_event: bool = False


class OptionCandidate(Contract):
    """A candidate contract surfaced by the Options Analysis Agent (BRD §13)."""

    underlying: str
    right: OptionRight
    strike: float = Field(gt=0)
    expiration: date
    premium: float = Field(ge=0)
    bid: float | None = Field(default=None, ge=0)
    ask: float | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)
    iv: float | None = Field(default=None, ge=0)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    liquidity: str | None = None


class CurrentHedge(Contract):
    """The hedge currently on the book, if any."""

    active: bool = False
    strategy_type: StrategyType | None = None
    legs: list[OptionLeg] = Field(default_factory=list)
    hedge_ratio: float | None = Field(default=None, ge=0)
    target_hedge_ratio: float | None = Field(default=None, ge=0)
    cost_basis: float | None = None
    hedge_pnl: float | None = None
    expiration: date | None = None


class HedgeObjective(Contract):
    """The user / project objective and hard budget the agents must respect."""

    max_hedge_budget_pct: float = Field(gt=0, le=1)
    drawdown_tolerance_pct: float = Field(gt=0, le=1)
    target_hedge_ratio: float | None = Field(default=None, ge=0)
    notes: str | None = None


class HedgeContext(Contract):
    """Standardized context assembled from the analysis agents (BRD §14)."""

    cycle_id: str
    timestamp: datetime
    portfolio_state: PortfolioState
    objective: HedgeObjective
    market_state: MarketState | None = None
    stock_state: list[StockView] = Field(default_factory=list)
    news_context: list[NewsItem] = Field(default_factory=list)
    option_candidates: list[OptionCandidate] = Field(default_factory=list)
    current_hedge: CurrentHedge = Field(default_factory=CurrentHedge)
    degraded_sections: list[str] = Field(
        default_factory=list,
        description="sections returned in a degraded state (a failed analysis agent)",
    )
    schema_version: int = 1
