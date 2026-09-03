"""News Analysis Agent tests — task P3-BE-8 (BRD §13).

A noise headline is dropped; a material event for a held name is kept and tagged
with that symbol. The affected set never contains a non-held ticker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs, build_agent_contexts
from backend.agents.news import analyze_news
from backend.models.hedge_context import NewsItem

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_HELD = ["AAPL", "NVDA"]

_FEED = [
    {"headline": "Markets little changed at midday", "ts": _NOW.isoformat(), "symbols": [], "source": "wire"},
    {"headline": "NVDA announces 10-for-1 stock split", "ts": _NOW.isoformat(), "symbols": ["NVDA"], "source": "wire"},
    {"headline": "Analyst reiterates hold on random small-cap XYZ", "ts": _NOW.isoformat(), "symbols": ["XYZ"], "source": "wire"},
]


def _inputs() -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-8",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 40_000.0,
                "equity": 60_000.0,
                "buying_power": 20_000.0,
                "positions": [
                    {"symbol": s, "qty": 100.0, "avg_price": 50.0, "market_value": 20_000.0}
                    for s in _HELD
                ],
            },
            "news_feed": _FEED,
        }
    )


def _run(client=None) -> list[NewsItem]:
    ctx = build_agent_contexts(_inputs())["news"]
    return analyze_news(ctx, client=client)


def test_noise_dropped_event_for_held_name_kept_and_tagged(mock_llm) -> None:
    mock_llm.response_content = json.dumps(
        {
            "verdicts": [
                {"index": 0, "is_event": False, "sentiment": 0.0, "symbols": []},
                {"index": 1, "is_event": True, "sentiment": 0.5, "symbols": ["NVDA"]},
                {"index": 2, "is_event": False, "sentiment": -0.1, "symbols": ["XYZ"]},
            ]
        }
    )
    out = _run(mock_llm)
    assert [item.headline for item in out] == ["NVDA announces 10-for-1 stock split"]
    kept = out[0]
    assert kept.symbols == ["NVDA"]
    assert kept.is_event is True
    assert kept.sentiment == pytest.approx(0.5)


def test_non_held_symbol_is_never_surfaced(mock_llm) -> None:
    mock_llm.response_content = json.dumps(
        {"verdicts": [{"index": 1, "is_event": True, "sentiment": 0.2, "symbols": ["NVDA", "TSLA"]}]}
    )
    out = _run(mock_llm)
    assert all("TSLA" not in item.symbols for item in out)
    assert out[0].symbols == ["NVDA"]


def test_sentiment_is_clamped_to_unit_range(mock_llm) -> None:
    mock_llm.response_content = json.dumps(
        {"verdicts": [{"index": 1, "is_event": True, "sentiment": 4.0, "symbols": ["NVDA"]}]}
    )
    assert _run(mock_llm)[0].sentiment == 1.0


def test_empty_feed_returns_empty_list(mock_llm) -> None:
    ctx = build_agent_contexts(
        AnalysisInputs.model_validate(
            {
                "cycle_id": "c",
                "timestamp": _NOW.isoformat(),
                "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
                "portfolio_state": {
                    "total_value": 1.0, "cash": 1.0, "equity": 0.0,
                    "buying_power": 0.0, "positions": [],
                },
                "news_feed": [],
            }
        )
    )["news"]
    assert analyze_news(ctx, client=mock_llm) == []


def test_fallback_keeps_only_held_symbol_items_when_llm_unavailable(mock_llm) -> None:
    # default FakeLLM body is '{"ok": true}' — no "verdicts" key → fallback path
    out = _run(mock_llm)
    assert [item.headline for item in out] == ["NVDA announces 10-for-1 stock split"]
    assert out[0].symbols == ["NVDA"]
    assert out[0].is_event is False
    assert out[0].sentiment is None
