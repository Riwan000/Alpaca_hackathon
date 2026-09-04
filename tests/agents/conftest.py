"""Shared fixtures for the orchestrator-node tests (P6-BE-2 … P6-BE-10).

``migrated_engine`` — a scratch SQLite database migrated to head, for the nodes
that persist (``RISK_CHECK`` → ``risk_checks``, ``EXECUTION`` → ``orders`` /
``execution_failures``, ``MONITORING`` → ``monitoring_state``, and every node's
``workflow_state`` transition rows).
``golden_context`` / ``golden_hedge_context`` — the recorded Phase 3
``HedgeContext`` fixture, as a raw dict and as a parsed model.
``analysis_inputs`` — a factory ``(cycle_id=None) -> AnalysisInputs`` for a full
graph ``invoke`` that starts at ``ANALYZING`` (routing / persistence tests).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.agents.context_builder import AnalysisInputs
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.models.hedge_context import HedgeContext

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_GOLDEN = _REPO_ROOT / "tests" / "fixtures" / "analyze" / "hedge_context_golden.json"


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    """A scratch SQLite database migrated to head, disposed on teardown."""
    db_url = f"sqlite:///{tmp_path / 'orch_nodes.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed:\n{proc.stdout}\n{proc.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def golden_context() -> dict[str, Any]:
    """The recorded Phase 3 ``HedgeContext`` fixture as a raw dict."""
    return json.loads(_GOLDEN.read_text("utf-8"))


@pytest.fixture
def golden_hedge_context(golden_context: dict[str, Any]) -> HedgeContext:
    """The recorded Phase 3 ``HedgeContext`` fixture, parsed."""
    return HedgeContext.model_validate(golden_context)


_INPUTS_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
def analysis_inputs() -> Callable[[str | None], AnalysisInputs]:
    """Factory for a valid :class:`AnalysisInputs` bundle — a DOWN market with an
    AAPL put chain, enough for the four strategy agents and the risk gate to run.

    Same shape proven end-to-end by ``test_graph_wired.py``; used by the routing
    and persistence tests that need to drive the graph from ``ANALYZING``.
    """
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    def _make(cycle_id: str | None = None) -> AnalysisInputs:
        return AnalysisInputs.model_validate(
            {
                "cycle_id": cycle_id or "cyc-routing",
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
                        {"symbol": "AAPL", "qty": 200.0, "avg_price": 150.0, "market_value": 30_000.0},
                    ],
                },
                "market_data": {
                    "index_symbol": "SPY",
                    "index_trend": "DOWN",
                    "index_price": 498.2,
                    "vix": 24.5,
                    "per_symbol": [
                        {"symbol": "AAPL", "last_price": 150.0, "prior_close": 152.0, "realized_vol": 0.30},
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
