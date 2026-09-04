"""Shared fixtures for the API integration tests.

``analysis_inputs`` is used by test_run_cycle.py and test_workflow_stream.py
to provide a valid AnalysisInputs bundle to the orchestrator graph stubs.
It mirrors the identical fixture in tests/agents/conftest.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs

_INPUTS_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
def analysis_inputs() -> Callable[[str | None], AnalysisInputs]:
    """Factory for a valid AnalysisInputs bundle used by POST /run-cycle tests."""
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    def _make(cycle_id: str | None = None) -> AnalysisInputs:
        return AnalysisInputs.model_validate(
            {
                "cycle_id": cycle_id or "cyc-api-test",
                "timestamp": _INPUTS_NOW.isoformat(),
                "objective": {
                    "max_hedge_budget_pct": 0.05,
                    "drawdown_tolerance_pct": 0.1,
                    "target_hedge_ratio": 0.8,
                },
                "portfolio_state": {
                    "total_value": 145_000.0,
                    "cash": 100_000.0,
                    "equity": 45_000.0,
                    "buying_power": 60_000.0,
                    "positions": [
                        {
                            "symbol": "AAPL",
                            "qty": 200.0,
                            "avg_price": 150.0,
                            "market_value": 30_000.0,
                        }
                    ],
                },
                "market_data": {
                    "index_symbol": "SPY",
                    "index_trend": "DOWN",
                    "index_price": 498.2,
                    "vix": 24.5,
                    "per_symbol": [
                        {
                            "symbol": "AAPL",
                            "last_price": 150.0,
                            "prior_close": 152.0,
                            "realized_vol": 0.30,
                        }
                    ],
                    "as_of": _INPUTS_NOW.isoformat(),
                },
                "news_feed": [
                    {
                        "headline": "AAPL guides revenue below consensus",
                        "ts": _INPUTS_NOW.isoformat(),
                        "body": "Apple cut its quarterly outlook.",
                        "symbols": ["AAPL"],
                        "source": "reuters",
                    }
                ],
                "option_chains": [
                    {
                        "underlying": "AAPL",
                        "spot": 150.0,
                        "quotes": [
                            {
                                "right": "PUT",
                                "strike": 145.0,
                                "expiration": expiry,
                                "bid": 3.10,
                                "ask": 3.20,
                                "volume": 900,
                                "open_interest": 4200,
                                "iv": 0.30,
                                "delta": -0.35,
                            },
                            {
                                "right": "PUT",
                                "strike": 135.0,
                                "expiration": expiry,
                                "bid": 1.05,
                                "ask": 1.15,
                                "volume": 700,
                                "open_interest": 3100,
                                "iv": 0.32,
                                "delta": -0.18,
                            },
                        ],
                    }
                ],
                "hedge_underlyings": ["AAPL"],
            }
        )

    return _make
