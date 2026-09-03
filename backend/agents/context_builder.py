"""Context builder — per-agent input slices (P3-BE-4, BRD §14).

BRD §14 requires that the system "avoid passing unnecessary raw information into
every LLM prompt" and that "a context builder ... provide each agent with the
information relevant to its task". This module is that builder.

:class:`AnalysisInputs` is the *full* per-cycle bundle assembled from the
integration layer (P3-BE-1..3): the portfolio blob, the market environment, the
raw news feed and the raw option chains. :func:`build_agent_contexts` projects it
into one small :class:`AgentContextSlice` per analysis agent, carrying only that
agent's required keys and none of the unrelated bulk:

===========  ====================================================================
agent        receives
===========  ====================================================================
portfolio    ``objective``, the full ``portfolio_state``, ``current_hedge``
stock        per-holding basics + per-symbol price bars + the index summary
market       the market environment (index / vol regime / sectors / macro)
news         the raw news feed + the held-symbol set
options      the raw option chains + hedge underlyings + the hedge budget
===========  ====================================================================

Only the Portfolio agent ever sees the full portfolio blob;
:func:`carries_full_portfolio` and :func:`log_agent_context_sizes` make that
checkable (the P3-BE-4 "Confirm" step).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import Field

from backend.models.common import Contract
from backend.models.enums import OptionRight
from backend.models.hedge_context import CurrentHedge, HedgeObjective, PortfolioState

__all__ = [
    "ANALYSIS_AGENTS",
    "AgentContextSlice",
    "AnalysisInputs",
    "MarketData",
    "OptionChain",
    "OptionQuoteRow",
    "RawNewsArticle",
    "SymbolBar",
    "build_agent_contexts",
    "carries_full_portfolio",
    "log_agent_context_sizes",
]

logger = logging.getLogger(__name__)

#: The Phase 3 analysis agents, in orchestration order (BRD §12–13).
ANALYSIS_AGENTS: tuple[str, ...] = ("portfolio", "stock", "market", "news", "options")


# --------------------------------------------------------------------------- #
# raw inputs — populated by the integration clients (P3-BE-1..3)
# --------------------------------------------------------------------------- #


class SymbolBar(Contract):
    """Per-holding price snapshot the Stock agent reasons from."""

    symbol: str
    last_price: float = Field(gt=0)
    prior_close: float | None = Field(default=None, gt=0)
    momentum: float | None = None
    realized_vol: float | None = Field(default=None, ge=0)


class MarketData(Contract):
    """Raw market-environment inputs (populated by P3-BE-1).

    ``per_symbol`` holds one :class:`SymbolBar` per held name — it is per-holding
    bulk and is routed to the Stock agent only, never to the Market agent.
    """

    index_symbol: str = "SPY"
    index_trend: str | None = None
    index_price: float | None = Field(default=None, gt=0)
    vix: float | None = Field(default=None, ge=0)
    sector_trends: dict[str, str] = Field(default_factory=dict)
    macro_notes: list[str] = Field(default_factory=list)
    per_symbol: list[SymbolBar] = Field(default_factory=list)
    as_of: datetime | None = None


class OptionQuoteRow(Contract):
    """One row of a raw option chain (pre relevance / liquidity filtering)."""

    right: OptionRight
    strike: float = Field(gt=0)
    expiration: date
    bid: float | None = Field(default=None, ge=0)
    ask: float | None = Field(default=None, ge=0)
    last: float | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)
    iv: float | None = Field(default=None, ge=0)
    delta: float | None = None


class OptionChain(Contract):
    """The raw chain for one underlying (populated by P3-BE-3)."""

    underlying: str
    spot: float | None = Field(default=None, gt=0)
    quotes: list[OptionQuoteRow] = Field(default_factory=list)


class RawNewsArticle(Contract):
    """A normalized-but-unfiltered article / event (populated by P3-BE-2).

    ``body`` is the bulk the News agent filters down; it is never forwarded to
    any other agent.
    """

    headline: str
    ts: datetime
    body: str | None = None
    symbols: list[str] = Field(default_factory=list)
    source: str | None = None


class AnalysisInputs(Contract):
    """The full per-cycle bundle handed to :func:`build_agent_contexts`."""

    cycle_id: str
    timestamp: datetime
    objective: HedgeObjective
    portfolio_state: PortfolioState
    current_hedge: CurrentHedge = Field(default_factory=CurrentHedge)
    market_data: MarketData = Field(default_factory=MarketData)
    news_feed: list[RawNewsArticle] = Field(default_factory=list)
    option_chains: list[OptionChain] = Field(default_factory=list)
    hedge_underlyings: list[str] = Field(
        default_factory=list,
        description="tickers a hedge may be built on; defaults to the held names",
    )
    equity_curve: list[float] = Field(
        default_factory=list,
        description="portfolio equity curve (oldest→newest) — Portfolio agent "
        "drawdown / volatility; empty means fall back to the snapshot metrics",
    )
    benchmark_returns: list[float] = Field(
        default_factory=list,
        description="index return series aligned to the equity curve — Portfolio "
        "agent beta; empty means keep the snapshot beta",
    )


# --------------------------------------------------------------------------- #
# per-agent slice
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentContextSlice:
    """The task-relevant projection handed to a single analysis agent.

    ``payload`` is a plain JSON-safe mapping (every value already ran through
    ``model_dump(mode="json")``), so it drops straight into a prompt and its
    serialized size is a faithful token-budget proxy.
    """

    agent: str
    cycle_id: str
    payload: Mapping[str, Any]

    @property
    def keys(self) -> frozenset[str]:
        """The top-level key set of the payload."""
        return frozenset(self.payload)

    def byte_size(self) -> int:
        """Serialized size of the payload in bytes (prompt-budget proxy)."""
        return len(json.dumps(self.payload, default=str, sort_keys=True).encode())


# --------------------------------------------------------------------------- #
# slicers — one per agent, each returns only that agent's task-relevant keys
# --------------------------------------------------------------------------- #


def _held_symbols(portfolio: PortfolioState) -> list[str]:
    return sorted({p.symbol for p in portfolio.positions})


def _holdings_basics(portfolio: PortfolioState) -> list[dict[str, Any]]:
    """Symbol / size only — no cost basis, P&L or account-level aggregates."""
    return [
        {
            "symbol": p.symbol,
            "qty": p.qty,
            "market_value": p.market_value,
            "asset_class": p.asset_class.value,
            "side": p.side.value,
        }
        for p in portfolio.positions
    ]


def _slice_portfolio(inp: AnalysisInputs) -> dict[str, Any]:
    """The one agent allowed the full portfolio blob (BRD §12 Portfolio agent)."""
    return {
        "objective": inp.objective.model_dump(mode="json"),
        "portfolio_state": inp.portfolio_state.model_dump(mode="json"),
        "current_hedge": inp.current_hedge.model_dump(mode="json"),
        "equity_curve": list(inp.equity_curve),
        "benchmark_returns": list(inp.benchmark_returns),
    }


def _slice_stock(inp: AnalysisInputs) -> dict[str, Any]:
    md = inp.market_data
    return {
        "total_value": inp.portfolio_state.total_value,
        "holdings": _holdings_basics(inp.portfolio_state),
        "per_symbol": [bar.model_dump(mode="json") for bar in md.per_symbol],
        "market_index": {
            "symbol": md.index_symbol,
            "trend": md.index_trend,
            "price": md.index_price,
            "vix": md.vix,
        },
    }


def _slice_market(inp: AnalysisInputs) -> dict[str, Any]:
    md = inp.market_data.model_dump(mode="json")
    md.pop("per_symbol", None)  # per-holding bulk belongs to the Stock agent
    return {"market_data": md}


def _slice_news(inp: AnalysisInputs) -> dict[str, Any]:
    return {
        "news_feed": [item.model_dump(mode="json") for item in inp.news_feed],
        "held_symbols": _held_symbols(inp.portfolio_state),
    }


def _slice_options(inp: AnalysisInputs) -> dict[str, Any]:
    underlyings = inp.hedge_underlyings or _held_symbols(inp.portfolio_state)
    return {
        "hedge_underlyings": list(underlyings),
        "budget": {
            "max_hedge_budget_pct": inp.objective.max_hedge_budget_pct,
            "target_hedge_ratio": inp.objective.target_hedge_ratio,
        },
        "portfolio_value": inp.portfolio_state.total_value,
        "option_chains": [chain.model_dump(mode="json") for chain in inp.option_chains],
    }


_SLICERS: dict[str, Any] = {
    "portfolio": _slice_portfolio,
    "stock": _slice_stock,
    "market": _slice_market,
    "news": _slice_news,
    "options": _slice_options,
}


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def build_agent_contexts(inputs: AnalysisInputs) -> dict[str, AgentContextSlice]:
    """Project ``inputs`` into one small slice per analysis agent (BRD §14).

    Every slice carries ``cycle_id`` and ``timestamp`` (cheap scalars needed for
    run logging and prompt headers) plus only the keys that agent's task needs.
    """
    slices: dict[str, AgentContextSlice] = {}
    for agent in ANALYSIS_AGENTS:
        payload: dict[str, Any] = {
            "cycle_id": inputs.cycle_id,
            "timestamp": inputs.timestamp.isoformat(),
        }
        payload.update(_SLICERS[agent](inputs))
        slices[agent] = AgentContextSlice(
            agent=agent, cycle_id=inputs.cycle_id, payload=payload
        )
    return slices


def carries_full_portfolio(payload: Mapping[str, Any]) -> bool:
    """True if ``payload`` embeds the full ``positions`` list — the bulk §14 warns against."""
    state = payload.get("portfolio_state")
    if not isinstance(state, Mapping):
        return False
    return bool(state.get("positions"))


def log_agent_context_sizes(
    slices: Mapping[str, AgentContextSlice],
    *,
    log: logging.Logger | None = None,
) -> dict[str, int]:
    """Emit one INFO line per agent with its payload size; return ``{agent: bytes}``.

    The P3-BE-4 "Confirm" step: the log shows each per-agent payload size and
    that only the Portfolio agent carries the full portfolio blob.
    """
    out = log or logger
    sizes: dict[str, int] = {}
    for agent, agent_slice in slices.items():
        size = agent_slice.byte_size()
        sizes[agent] = size
        out.info(
            "context slice: agent=%s bytes=%d keys=%s full_portfolio=%s",
            agent,
            size,
            ",".join(sorted(agent_slice.keys)),
            carries_full_portfolio(agent_slice.payload),
        )
    return sizes
