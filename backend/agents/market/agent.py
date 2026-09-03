"""Market Analysis Agent — task P3-BE-7 (BRD §13).

Produces the :class:`~backend.models.hedge_context.MarketState` section from the
market-environment slice (index trend, index price, VIX, sector trends, macro
notes — the per-holding bars are *not* in this slice by design).

``index_trend`` / ``vix`` / ``as_of`` are passed straight through from the P3-BE-1
data. ``regime`` is a single classification token: the LLM picks one of
:class:`~backend.models.enums.MarketRegime`, and a VIX + trend rule fills one in
whenever the model is unavailable or answers off-enum.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from openai import OpenAI
from pydantic import Field

from backend.agents.base import AgentError, complete_json
from backend.agents.context_builder import AgentContextSlice
from backend.agents.prompts import render as render_prompt
from backend.models.common import Contract
from backend.models.enums import MarketRegime
from backend.models.hedge_context import MarketState

__all__ = ["MarketAgentInput", "analyze_market"]

_HIGH_VOL_VIX = 28.0
_RISK_OFF_VIX = 20.0


class _MarketDataView(Contract):
    index_symbol: str = "SPY"
    index_trend: str | None = None
    index_price: float | None = None
    vix: float | None = None
    sector_trends: dict[str, str] = Field(default_factory=dict)
    macro_notes: list[str] = Field(default_factory=list)
    as_of: datetime | None = None


class MarketAgentInput(Contract):
    """The Market agent's validated view of its context slice."""

    cycle_id: str
    timestamp: datetime
    market_data: _MarketDataView


def _rule_regime(vix: float | None, index_trend: str | None) -> MarketRegime:
    trend = (index_trend or "").strip().upper()
    if vix is not None and vix >= _HIGH_VOL_VIX:
        return MarketRegime.HIGH_VOL
    if trend in {"DOWN", "BEARISH"} or (vix is not None and vix >= _RISK_OFF_VIX):
        return MarketRegime.RISK_OFF
    if trend in {"UP", "BULLISH"}:
        return MarketRegime.RISK_ON
    return MarketRegime.NEUTRAL


def _llm_regime(view: _MarketDataView, client: OpenAI | None) -> MarketRegime | None:
    summary: dict[str, Any] = {
        "index_trend": view.index_trend,
        "vix": view.vix,
        "sector_trends": view.sector_trends,
        "macro_notes": view.macro_notes,
    }
    prompt = render_prompt("market", summary=str(summary))
    try:
        raw = complete_json(prompt.system, prompt.user, client=client)
    except AgentError:
        return None
    try:
        return MarketRegime(str(raw.get("regime", "")).strip().upper())
    except ValueError:
        return None


def analyze_market(
    ctx: AgentContextSlice, *, client: OpenAI | None = None
) -> MarketState:
    """Return the :class:`MarketState` section for ``ctx`` (BRD §13)."""
    data = MarketAgentInput.model_validate(dict(ctx.payload))
    view = data.market_data
    regime = _llm_regime(view, client) or _rule_regime(view.vix, view.index_trend)
    return MarketState(
        regime=regime.value,
        index_trend=view.index_trend,
        vix=view.vix,
        as_of=view.as_of,
    )
