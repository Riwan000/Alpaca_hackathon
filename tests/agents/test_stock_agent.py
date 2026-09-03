"""Stock Analysis Agent tests — task P3-BE-6 (BRD §12–13).

One schema-valid ``StockView`` per holding; deterministic momentum / key levels
from the price bar; a holding with no bar is handled, not skipped.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs, build_agent_contexts
from backend.agents.stock import analyze_stocks
from backend.models.hedge_context import StockView

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_HELD = ["AAPL", "NVDA", "ILLIQ"]  # ILLIQ has no price bar


def _inputs() -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-6",
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
            "market_data": {
                "per_symbol": [
                    {
                        "symbol": "AAPL",
                        "last_price": 110.0,
                        "prior_close": 100.0,
                        "momentum": None,
                        "realized_vol": 0.35,
                    },
                    {
                        "symbol": "NVDA",
                        "last_price": 95.0,
                        "prior_close": 100.0,
                        "momentum": -0.05,
                        "realized_vol": 0.20,
                    },
                ],
            },
        }
    )


def _run(client=None) -> list[StockView]:
    ctx = build_agent_contexts(_inputs())["stock"]
    return analyze_stocks(ctx, client=client)


def test_one_schema_valid_view_per_holding(mock_llm) -> None:
    views = _run(mock_llm)
    assert [v.symbol for v in views] == _HELD
    for view in views:
        StockView.model_validate(view.model_dump())
        assert view.risk_note


def test_unknown_symbol_is_handled_not_dropped(mock_llm) -> None:
    views = {v.symbol: v for v in _run(mock_llm)}
    illiq = views["ILLIQ"]
    assert illiq.risk_note == "no market data available"
    assert illiq.momentum is None
    assert illiq.key_levels == []


def test_momentum_is_computed_from_the_bar_when_absent(mock_llm) -> None:
    views = {v.symbol: v for v in _run(mock_llm)}
    # AAPL bar carries no momentum → last/prior - 1 = 0.10
    assert views["AAPL"].momentum == pytest.approx(0.10)
    # NVDA bar carries an explicit momentum → passed straight through
    assert views["NVDA"].momentum == pytest.approx(-0.05)


def test_key_levels_are_deterministic_and_sorted(mock_llm) -> None:
    aapl = {v.symbol: v for v in _run(mock_llm)}["AAPL"]
    # prior_close 100, last 110, ±(110 * 0.35) band → 71.5 / 100 / 110 (capped at 3)
    assert aapl.key_levels == sorted(aapl.key_levels)
    assert len(aapl.key_levels) <= 3
    assert 100.0 in aapl.key_levels


def test_llm_notes_are_used_when_present(mock_llm) -> None:
    mock_llm.response_content = json.dumps(
        {"notes": {"AAPL": "high beta, momentum stretched", "NVDA": "cooling off"}}
    )
    views = {v.symbol: v for v in _run(mock_llm)}
    assert views["AAPL"].risk_note == "high beta, momentum stretched"
    assert views["NVDA"].risk_note == "cooling off"


def test_falls_back_to_a_deterministic_note_when_llm_gives_nothing(mock_llm) -> None:
    # default FakeLLM body is '{"ok": true}' — no "notes" key
    views = {v.symbol: v for v in _run(mock_llm)}
    assert "volatility" in views["AAPL"].risk_note
    assert "momentum" in views["AAPL"].risk_note


def test_null_or_non_string_llm_note_falls_back_not_stringified(mock_llm) -> None:
    mock_llm.response_content = json.dumps({"notes": {"AAPL": None, "NVDA": {"x": 1}}})
    views = {v.symbol: v for v in _run(mock_llm)}
    assert views["AAPL"].risk_note != "None"
    assert "volatility" in views["AAPL"].risk_note  # deterministic fallback used
    assert views["NVDA"].risk_note not in ("{'x': 1}", "None")
