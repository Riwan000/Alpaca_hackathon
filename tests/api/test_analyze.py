"""``POST /analyze`` tests — task P3-BE-12 (BRD §11, §31).

* a healthy cycle → ``200`` with a body that validates as ``HedgeContext`` and a
  persisted ``portfolio_snapshots`` row + its ``positions`` + one ``agent_runs``
  row per analysis agent;
* the same cycle is immediately visible through the read-back endpoints
  (shared engine);
* one agent forced to fail → still ``200``, the section flagged ``degraded`` and
  its ``agent_runs`` row carrying the error (Phase 3 acceptance, no crash).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.agents import ANALYSIS_AGENTS
from backend.agents.assembler import ANALYSIS_AGENT_FNS
from backend.agents.base import AgentError
from backend.agents.context_builder import AnalysisInputs
from backend.api import create_app
from backend.api.analyze import provide_analysis_inputs
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.agent_runs_repo import AgentRunRepository
from backend.db.repository import PortfolioSnapshotRepository
from backend.models.hedge_context import HedgeContext

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _canned_inputs() -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-analyze-test",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 140_500.0,
                "cash": 100_000.0,
                "equity": 40_500.0,
                "buying_power": 50_000.0,
                "positions": [
                    {"symbol": "AAPL", "qty": 100.0, "avg_price": 150.0, "market_value": 22_500.0},
                    {"symbol": "NVDA", "qty": 150.0, "avg_price": 100.0, "market_value": 18_000.0},
                ],
            },
            "market_data": {
                "index_symbol": "SPY",
                "index_trend": "DOWN",
                "vix": 24.5,
                "per_symbol": [
                    {"symbol": "AAPL", "last_price": 150.0, "prior_close": 152.0},
                    {"symbol": "NVDA", "last_price": 120.0, "prior_close": 118.0},
                ],
                "as_of": _NOW.isoformat(),
            },
            "news_feed": [
                {
                    "headline": "AAPL guides revenue below consensus",
                    "ts": _NOW.isoformat(),
                    "body": "Apple cut its quarterly outlook.",
                    "symbols": ["AAPL"],
                    "source": "reuters",
                },
            ],
            "option_chains": [
                {
                    "underlying": "AAPL",
                    "spot": 150.0,
                    "quotes": [
                        {
                            "right": "PUT",
                            "strike": 145.0,
                            "expiration": _EXPIRY,
                            "bid": 3.10,
                            "ask": 3.20,
                            "volume": 900,
                            "open_interest": 4200,
                            "iv": 0.30,
                            "delta": -0.35,
                        }
                    ],
                }
            ],
            "hedge_underlyings": ["AAPL"],
        }
    )


@pytest.fixture
def analyze_ctx(tmp_path: Path, mock_llm) -> Iterator[tuple[TestClient, object]]:
    db_url = f"sqlite:///{tmp_path / 'analyze_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    app.dependency_overrides[provide_analysis_inputs] = _canned_inputs
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_analyze_returns_a_valid_hedge_context(analyze_ctx) -> None:
    client, _ = analyze_ctx
    response = client.post("/analyze")

    assert response.status_code == 200, response.text
    ctx = HedgeContext.model_validate(response.json())
    assert ctx.cycle_id == "cyc-analyze-test"
    assert ctx.degraded_sections == []
    # the portfolio agent recomputed the exposure numbers
    assert ctx.portfolio_state.gross_exposure == pytest.approx(40_500.0)
    assert [v.symbol for v in ctx.stock_state] == ["AAPL", "NVDA"]


def test_analyze_persists_snapshot_positions_and_runs(analyze_ctx) -> None:
    client, engine = analyze_ctx
    ctx = HedgeContext.model_validate(client.post("/analyze").json())

    snap_repo = PortfolioSnapshotRepository(engine)
    latest = snap_repo.latest()
    assert latest is not None and latest.cycle_id == ctx.cycle_id
    assert latest.id is not None
    assert [p.symbol for p in snap_repo.positions_for(latest.id)] == ["AAPL", "NVDA"]

    runs = AgentRunRepository(engine).list_for_cycle(ctx.cycle_id)
    assert [r.agent_name for r in runs] == list(ANALYSIS_AGENTS)
    assert all(r.duration_ms is not None and r.duration_ms >= 0 for r in runs)
    assert all(r.error is None for r in runs)


def test_analyze_cycle_is_visible_through_readback(analyze_ctx) -> None:
    client, _ = analyze_ctx
    ctx = HedgeContext.model_validate(client.post("/analyze").json())

    latest = client.get("/portfolio/latest").json()
    assert latest["cycle_id"] == ctx.cycle_id
    assert {p["symbol"] for p in latest["positions"]} == {"AAPL", "NVDA"}

    runs = client.get("/agent-runs", params={"cycle_id": ctx.cycle_id}).json()
    assert [r["agent_name"] for r in runs] == list(ANALYSIS_AGENTS)


def test_analyze_degrades_a_failing_agent_but_still_returns_200(
    analyze_ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: object, **_k: object) -> object:
        raise AgentError("killed for the test")

    monkeypatch.setitem(ANALYSIS_AGENT_FNS, "news", _boom)
    client, engine = analyze_ctx

    response = client.post("/analyze")
    assert response.status_code == 200, response.text
    ctx = HedgeContext.model_validate(response.json())
    assert ctx.degraded_sections == ["news_context"]
    assert ctx.news_context == []

    runs = {r.agent_name: r for r in AgentRunRepository(engine).list_for_cycle(ctx.cycle_id)}
    assert runs["news"].error is not None and "killed for the test" in runs["news"].error
    assert runs["news"].outputs is None
