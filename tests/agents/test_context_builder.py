"""Context-builder tests — task P3-BE-4 (BRD §14).

Each analysis agent's slice must (a) contain exactly its required keys and
(b) omit every other agent's bulk. Asserted here by key set + a serialized-size
bound, plus the "Confirm" check that only the Portfolio agent carries the full
portfolio blob.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from backend.agents.context_builder import (
    ANALYSIS_AGENTS,
    AnalysisInputs,
    build_agent_contexts,
    carries_full_portfolio,
    log_agent_context_sizes,
)

# --------------------------------------------------------------------------- #
# fixture — a deliberately bulky bundle so the size bounds mean something
# --------------------------------------------------------------------------- #

_SYMBOLS = [f"SYM{i:02d}" for i in range(20)]
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


def _positions() -> list[dict[str, Any]]:
    return [
        {
            "symbol": sym,
            "qty": 100.0 + idx,
            "avg_price": 90.0 + idx,
            "market_value": 10_000.0 + idx * 250,
            "asset_class": "EQUITY",
            "side": "BUY",
            "unrealized_pl": 1_500.0 - idx * 10,
        }
        for idx, sym in enumerate(_SYMBOLS)
    ]


def _raw_inputs() -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-4",
            "timestamp": _NOW.isoformat(),
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.1,
                "target_hedge_ratio": 0.2,
                "notes": "capital preservation into year end",
            },
            "portfolio_state": {
                "total_value": 1_000_000.0,
                "cash": 200_000.0,
                "equity": 800_000.0,
                "buying_power": 400_000.0,
                "positions": _positions(),
                "gross_exposure": 800_000.0,
                "net_exposure": 760_000.0,
                "concentration_hhi": 0.09,
                "drawdown": -0.07,
                "max_drawdown": -0.12,
                "volatility": 0.19,
                "beta": 1.1,
            },
            "current_hedge": {"active": False},
            "market_data": {
                "index_symbol": "SPY",
                "index_trend": "DOWN",
                "index_price": 498.2,
                "vix": 24.5,
                "sector_trends": {"tech": "DOWN", "energy": "UP", "financials": "FLAT"},
                "macro_notes": ["Fed on hold", "PMI contracting", "credit spreads widening"],
                "per_symbol": [
                    {
                        "symbol": sym,
                        "last_price": 100.0 + idx,
                        "prior_close": 101.0 + idx,
                        "momentum": -0.2 + idx * 0.01,
                        "realized_vol": 0.25,
                    }
                    for idx, sym in enumerate(_SYMBOLS)
                ],
                "as_of": _NOW.isoformat(),
            },
            "news_feed": [
                {
                    "headline": f"Headline {i} about the tape and rates",
                    "ts": _NOW.isoformat(),
                    "body": "lorem ipsum dolor sit amet " * 12,
                    "symbols": [_SYMBOLS[i % len(_SYMBOLS)]],
                    "source": "reuters",
                }
                for i in range(10)
            ],
            "option_chains": [
                {
                    "underlying": sym,
                    "spot": 100.0,
                    "quotes": [
                        {
                            "right": "PUT",
                            "strike": 80.0 + k,
                            "expiration": "2026-12-18",
                            "bid": 1.0 + k * 0.1,
                            "ask": 1.2 + k * 0.1,
                            "last": 1.1 + k * 0.1,
                            "volume": 100 + k,
                            "open_interest": 500 + k * 3,
                            "iv": 0.21,
                            "delta": -0.3,
                        }
                        for k in range(20)
                    ],
                }
                for sym in _SYMBOLS[:3]
            ],
            "hedge_underlyings": ["SPY"],
        }
    )


_EXPECTED_KEYS: dict[str, set[str]] = {
    "portfolio": {
        "cycle_id",
        "timestamp",
        "objective",
        "portfolio_state",
        "current_hedge",
        "equity_curve",
        "benchmark_returns",
    },
    "stock": {"cycle_id", "timestamp", "total_value", "holdings", "per_symbol", "market_index"},
    "market": {"cycle_id", "timestamp", "market_data"},
    "news": {"cycle_id", "timestamp", "news_feed", "held_symbols"},
    "options": {
        "cycle_id",
        "timestamp",
        "hedge_underlyings",
        "budget",
        "portfolio_value",
        "option_chains",
    },
}


@pytest.fixture
def slices():
    return build_agent_contexts(_raw_inputs())


# --------------------------------------------------------------------------- #
# key sets
# --------------------------------------------------------------------------- #


def test_one_slice_per_analysis_agent(slices):
    assert set(slices) == set(ANALYSIS_AGENTS)
    for agent, agent_slice in slices.items():
        assert agent_slice.agent == agent
        assert agent_slice.cycle_id == "cyc-p3-be-4"


@pytest.mark.parametrize("agent", ANALYSIS_AGENTS)
def test_slice_has_exactly_its_required_keys(slices, agent):
    assert set(slices[agent].payload) == _EXPECTED_KEYS[agent]
    assert slices[agent].keys == frozenset(_EXPECTED_KEYS[agent])


# --------------------------------------------------------------------------- #
# omits unrelated bulk
# --------------------------------------------------------------------------- #


def test_full_portfolio_blob_reaches_portfolio_agent_only(slices):
    assert carries_full_portfolio(slices["portfolio"].payload) is True
    for agent in ("stock", "market", "news", "options"):
        assert carries_full_portfolio(slices[agent].payload) is False
        assert "portfolio_state" not in slices[agent].payload


def test_news_feed_reaches_news_agent_only(slices):
    assert len(slices["news"].payload["news_feed"]) == 10
    for agent in ("portfolio", "stock", "market", "options"):
        assert "news_feed" not in slices[agent].payload


def test_option_chains_reach_options_agent_only(slices):
    assert len(slices["options"].payload["option_chains"]) == 3
    for agent in ("portfolio", "stock", "market", "news"):
        assert "option_chains" not in slices[agent].payload


def test_market_agent_gets_environment_without_per_holding_bulk(slices):
    market_data = slices["market"].payload["market_data"]
    assert "per_symbol" not in market_data
    assert market_data["sector_trends"] and market_data["macro_notes"]


def test_stock_agent_gets_per_symbol_bars_but_not_account_aggregates(slices):
    payload = slices["stock"].payload
    assert {bar["symbol"] for bar in payload["per_symbol"]} == set(_SYMBOLS)
    # holdings are symbol/size only — no cost basis, P&L, cash, HHI, beta
    assert all(set(h) == {"symbol", "qty", "market_value", "asset_class", "side"} for h in payload["holdings"])
    assert "sector_trends" not in payload["market_index"]


def test_news_agent_gets_held_symbols_not_positions(slices):
    held = slices["news"].payload["held_symbols"]
    assert held == sorted(set(_SYMBOLS))
    assert all(isinstance(sym, str) for sym in held)


def test_options_agent_gets_budget_and_underlyings_not_positions(slices):
    payload = slices["options"].payload
    assert payload["hedge_underlyings"] == ["SPY"]
    assert payload["budget"] == {"max_hedge_budget_pct": 0.05, "target_hedge_ratio": 0.2}
    assert payload["portfolio_value"] == 1_000_000.0


def test_options_underlyings_default_to_held_names_when_unset():
    raw = _raw_inputs().model_dump(mode="json")
    raw["hedge_underlyings"] = []
    payload = build_agent_contexts(AnalysisInputs.model_validate(raw))["options"].payload
    assert payload["hedge_underlyings"] == sorted(set(_SYMBOLS))


# --------------------------------------------------------------------------- #
# size bound
#
# The three heavy blobs — the positions list, the raw news feed, the option
# chains — each belong to exactly one agent. The bound below is load-bearing:
# for every agent that must EXCLUDE a given blob, its slice has to be smaller
# than "the whole bundle minus most of that blob", so copying the blob in would
# fail the assertion (the exact key-set test alone would also catch it, but the
# plan asks for a size bound and this makes it real).
# --------------------------------------------------------------------------- #


def _blob_bytes(obj: Any) -> int:
    return len(json.dumps(obj, default=str, sort_keys=True).encode())


def _full_bytes() -> int:
    return _blob_bytes(_raw_inputs().model_dump(mode="json"))


def test_every_slice_is_a_strict_subset_of_the_full_bundle(slices):
    full_bytes = _full_bytes()
    for agent, agent_slice in slices.items():
        assert 0 < agent_slice.byte_size() < full_bytes, agent


def test_slice_excluding_a_heavy_blob_is_smaller_than_the_bundle_minus_that_blob(slices):
    raw = _raw_inputs().model_dump(mode="json")
    full_bytes = _full_bytes()
    # blob -> the agents whose slice must not carry it
    excluded_by = {
        _blob_bytes(raw["portfolio_state"]["positions"]): ("stock", "market", "news", "options"),
        _blob_bytes(raw["news_feed"]): ("portfolio", "stock", "market", "options"),
        _blob_bytes(raw["option_chains"]): ("portfolio", "stock", "market", "news"),
    }
    slack = 512  # key names + scalars a slice legitimately adds back
    for blob_bytes, agents in excluded_by.items():
        ceiling = full_bytes - blob_bytes + slack
        for agent in agents:
            assert slices[agent].byte_size() < ceiling, (agent, blob_bytes)


def test_summary_only_market_agent_is_tiny(slices):
    # the market slice drops every heavy blob — it is a pure environment summary.
    assert slices["market"].byte_size() < _full_bytes() * 0.1


def test_no_slice_smuggles_a_second_agents_bulk(slices):
    # portfolio slice must not contain the raw news bodies or option quotes.
    portfolio_json = json.dumps(slices["portfolio"].payload)
    assert "lorem ipsum" not in portfolio_json
    assert "open_interest" not in portfolio_json


# --------------------------------------------------------------------------- #
# Confirm — log the per-agent payload sizes
# --------------------------------------------------------------------------- #


def test_log_agent_context_sizes_reports_every_agent(slices, caplog):
    with caplog.at_level(logging.INFO, logger="backend.agents.context_builder"):
        sizes = log_agent_context_sizes(slices)

    assert set(sizes) == set(ANALYSIS_AGENTS)
    assert all(size > 0 for size in sizes.values())

    lines = [rec.message for rec in caplog.records if "context slice:" in rec.message]
    assert len(lines) == len(ANALYSIS_AGENTS)
    assert sum("full_portfolio=True" in line for line in lines) == 1
    assert any("agent=portfolio" in line and "full_portfolio=True" in line for line in lines)


# --------------------------------------------------------------------------- #
# boundary validation
# --------------------------------------------------------------------------- #


def test_analysis_inputs_rejects_unknown_keys():
    raw = _raw_inputs().model_dump(mode="json")
    raw["surprise"] = "not a field"
    with pytest.raises(ValidationError):
        AnalysisInputs.model_validate(raw)
