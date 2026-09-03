"""Stock Analysis Agent — task P3-BE-6 (BRD §12–13).

Emits one :class:`~backend.models.hedge_context.StockView` per holding:

* ``momentum`` and ``key_levels`` are computed from the per-symbol price bar the
  context builder attached (deterministic);
* ``risk_note`` is a short phrase from the LLM — one batched call for the whole
  book — with a deterministic fallback per symbol when the model is unavailable
  or returns nothing usable.

A holding with no market data (an unknown / illiquid symbol) still gets a
``StockView`` row, tagged ``"no market data available"`` with empty levels.
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
from backend.models.hedge_context import StockView

__all__ = ["StockAgentInput", "analyze_stocks"]

_KEY_LEVELS = 3
_PRICE_DP = 2
_NO_DATA_NOTE = "no market data available"
_NOTE_MAX_CHARS = 120
_HIGH_VOL = 0.30


class _Bar(Contract):
    symbol: str
    last_price: float
    prior_close: float | None = None
    momentum: float | None = None
    realized_vol: float | None = None


class _Holding(Contract):
    symbol: str
    qty: float
    market_value: float
    asset_class: str
    side: str


class StockAgentInput(Contract):
    """The Stock agent's validated view of its context slice."""

    cycle_id: str
    timestamp: datetime
    total_value: float
    holdings: list[_Holding] = Field(default_factory=list)
    per_symbol: list[_Bar] = Field(default_factory=list)
    market_index: dict[str, Any] = Field(default_factory=dict)


def _momentum(bar: _Bar) -> float | None:
    if bar.momentum is not None:
        return bar.momentum
    if bar.prior_close:
        return bar.last_price / bar.prior_close - 1.0
    return None


def _key_levels(bar: _Bar) -> list[float]:
    levels: set[float] = {round(bar.last_price, _PRICE_DP)}
    if bar.prior_close:
        levels.add(round(bar.prior_close, _PRICE_DP))
    if bar.realized_vol:
        band = bar.last_price * bar.realized_vol
        levels.add(round(bar.last_price - band, _PRICE_DP))
        levels.add(round(bar.last_price + band, _PRICE_DP))
    return sorted(levels)[:_KEY_LEVELS]


def _fallback_note(bar: _Bar | None, momentum: float | None) -> str:
    if bar is None:
        return _NO_DATA_NOTE
    parts: list[str] = []
    if bar.realized_vol is not None:
        vol_word = "elevated" if bar.realized_vol >= _HIGH_VOL else "moderate"
        parts.append(f"{vol_word} volatility (σ≈{bar.realized_vol:.2f})")
    if momentum is not None:
        parts.append(f"{'positive' if momentum >= 0 else 'negative'} momentum")
    return ", ".join(parts) or "no notable signal"


def _llm_notes(
    holdings: list[_Holding], bars: dict[str, _Bar], client: OpenAI | None
) -> dict[str, str]:
    payload = [
        {
            "symbol": h.symbol,
            "momentum": _momentum(bars[h.symbol]) if h.symbol in bars else None,
            "realized_vol": bars[h.symbol].realized_vol if h.symbol in bars else None,
        }
        for h in holdings
    ]
    prompt = render_prompt("stock", payload=str(payload))
    try:
        raw = complete_json(prompt.system, prompt.user, client=client)
    except AgentError:
        return {}
    notes = raw.get("notes")
    if not isinstance(notes, dict):
        return {}
    # only accept a real, non-empty string — a null / dict / list value from the
    # model must fall through to the deterministic note, not become "None".
    return {
        str(sym): note.strip()[:_NOTE_MAX_CHARS]
        for sym, note in notes.items()
        if isinstance(note, str) and note.strip()
    }


def analyze_stocks(
    ctx: AgentContextSlice, *, client: OpenAI | None = None
) -> list[StockView]:
    """Return one :class:`StockView` per holding for ``ctx`` (BRD §12)."""
    data = StockAgentInput.model_validate(dict(ctx.payload))
    bars = {bar.symbol: bar for bar in data.per_symbol}
    notes = _llm_notes(data.holdings, bars, client) if data.holdings else {}

    views: list[StockView] = []
    for holding in data.holdings:
        bar = bars.get(holding.symbol)
        momentum = _momentum(bar) if bar is not None else None
        note = notes.get(holding.symbol) or _fallback_note(bar, momentum)
        views.append(
            StockView(
                symbol=holding.symbol,
                risk_note=note,
                momentum=momentum,
                key_levels=_key_levels(bar) if bar is not None else [],
            )
        )
    return views
