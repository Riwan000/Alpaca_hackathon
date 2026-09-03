"""News Analysis Agent — task P3-BE-8 (BRD §13).

Filters the raw news feed down to what matters for the book: an item is kept
only if the LLM marks it a **material event** or it names a **held symbol**;
routine headlines with neither are dropped. Kept items carry a sentiment score
and the affected tickers, and the affected set is always intersected with the
held symbols so the agent can never surface a name the portfolio does not hold.

The LLM does one batched classification call. If it is unavailable, a
deterministic fallback keeps exactly the held-symbol items (no event tagging,
no sentiment).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from openai import OpenAI
from pydantic import Field

from backend.agents.base import AgentError, complete_json
from backend.agents.context_builder import AgentContextSlice
from backend.models.common import Contract
from backend.models.hedge_context import NewsItem

__all__ = ["NewsAgentInput", "analyze_news"]

_SENTIMENT_MIN = -1.0
_SENTIMENT_MAX = 1.0
_BODY_EXCERPT_CHARS = 280

_SYSTEM = (
    "You triage financial news. For each article decide: is_event (true only for "
    "a material corporate or market event, not a routine headline), sentiment "
    "(number from -1 to 1) and symbols (tickers materially affected). Reply with "
    'JSON {"verdicts": [{"index": <int>, "is_event": <bool>, "sentiment": '
    "<number>, \"symbols\": [<ticker>, ...]}]} and nothing else."
)


class _RawArticle(Contract):
    headline: str
    ts: datetime
    body: str | None = None
    symbols: list[str] = Field(default_factory=list)
    source: str | None = None


class NewsAgentInput(Contract):
    """The News agent's validated view of its context slice."""

    cycle_id: str
    timestamp: datetime
    news_feed: list[_RawArticle] = Field(default_factory=list)
    held_symbols: list[str] = Field(default_factory=list)


def _clamp_sentiment(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return max(_SENTIMENT_MIN, min(_SENTIMENT_MAX, float(value)))


def _verdicts_by_index(
    articles: list[_RawArticle], client: OpenAI | None
) -> dict[int, dict[str, Any]]:
    payload = [
        {
            "index": i,
            "headline": art.headline,
            "body": (art.body or "")[:_BODY_EXCERPT_CHARS],
            "symbols": list(art.symbols),
        }
        for i, art in enumerate(articles)
    ]
    try:
        raw = complete_json(_SYSTEM, str(payload), client=client)
    except AgentError:
        return {}
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for entry in verdicts:
        idx = entry.get("index") if isinstance(entry, dict) else None
        if isinstance(idx, int) and not isinstance(idx, bool):
            out[idx] = entry
    return out


def analyze_news(
    ctx: AgentContextSlice, *, client: OpenAI | None = None
) -> list[NewsItem]:
    """Return the relevance-filtered ``news_context`` for ``ctx`` (BRD §13)."""
    data = NewsAgentInput.model_validate(dict(ctx.payload))
    if not data.news_feed:
        return []

    held = {s.strip().upper() for s in data.held_symbols}
    verdicts = _verdicts_by_index(data.news_feed, client)

    kept: list[NewsItem] = []
    for i, art in enumerate(data.news_feed):
        verdict = verdicts.get(i, {})
        llm_symbols = verdict.get("symbols")
        named = {str(s).strip().upper() for s in llm_symbols} if isinstance(llm_symbols, list) else set()
        named |= {s.strip().upper() for s in art.symbols}
        affected = sorted(named & held)
        is_event = bool(verdict.get("is_event"))
        if not is_event and not affected:
            continue
        kept.append(
            NewsItem(
                headline=art.headline,
                ts=art.ts,
                symbols=affected,
                source=art.source,
                sentiment=_clamp_sentiment(verdict.get("sentiment")),
                is_event=is_event,
            )
        )
    return kept
