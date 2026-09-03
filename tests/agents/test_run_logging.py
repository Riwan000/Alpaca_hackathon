"""Per-agent ``agent_runs`` logging — task P3-BE-11 (BRD §14, §31).

Every analysis-agent invocation inside :func:`assemble_hedge_context` writes
exactly one ``agent_runs`` row when ``run_repo`` is supplied:

* a healthy pass → one row per agent, in ``ANALYSIS_AGENTS`` order, each closed
  with ``outputs`` and a non-negative ``duration_ms``;
* a killed agent → its row is closed with ``error`` set and ``outputs`` still
  ``NULL``, the other agents' rows are unaffected, and the pass still returns a
  schema-valid ``HedgeContext``;
* run logging is optional and best-effort — omitting ``run_repo`` writes nothing,
  and a repository that raises never breaks the pass.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine

from backend.agents import ANALYSIS_AGENTS
from backend.agents.assembler import ANALYSIS_AGENT_FNS, assemble_hedge_context
from backend.agents.base import AgentError
from backend.agents.context_builder import AnalysisInputs
from backend.db import normalize_driver
from backend.db.agent_runs_repo import AgentRunRepository
from backend.models.hedge_context import HedgeContext

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()


def _inputs(cycle_id: str) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": cycle_id,
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
                    {"symbol": "AAPL", "last_price": 150.0, "prior_close": 152.0, "realized_vol": 0.28},
                    {"symbol": "NVDA", "last_price": 120.0, "prior_close": 118.0, "realized_vol": 0.35},
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
def run_repo(_migrated_sqlite_url: str) -> AgentRunRepository:
    engine = create_engine(normalize_driver(_migrated_sqlite_url), future=True)
    return AgentRunRepository(engine)


def _boom(*_a: Any, **_k: Any) -> Any:
    raise AgentError("killed for the test")


def test_healthy_pass_writes_exactly_one_row_per_agent(mock_llm, run_repo) -> None:
    cid = "cyc-runlog-healthy"
    ctx = assemble_hedge_context(_inputs(cid), client=mock_llm, run_repo=run_repo)

    assert isinstance(ctx, HedgeContext)
    runs = run_repo.list_for_cycle(cid)

    # one row per analysis agent, in orchestration order
    assert [r.agent_name for r in runs] == list(ANALYSIS_AGENTS)
    # every row is closed with timing and a success payload
    for run in runs:
        assert run.duration_ms is not None and run.duration_ms >= 0
        assert run.finished_at is not None
        assert run.error is None
        assert isinstance(run.inputs, dict) and run.inputs
        assert isinstance(run.outputs, dict)
    # each row's outputs is keyed by the HedgeContext section that agent fills
    sections = {r.agent_name: next(iter(r.outputs)) for r in runs}
    assert sections == {
        "portfolio": "portfolio_state",
        "stock": "stock_state",
        "market": "market_state",
        "news": "news_context",
        "options": "option_candidates",
    }


def test_killed_agent_row_carries_the_error_and_no_outputs(mock_llm, run_repo) -> None:
    cid = "cyc-runlog-killed"
    fns = {**ANALYSIS_AGENT_FNS, "news": _boom}

    ctx = assemble_hedge_context(_inputs(cid), client=mock_llm, run_repo=run_repo, agent_fns=fns)
    assert ctx.degraded_sections == ["news_context"]

    runs = {r.agent_name: r for r in run_repo.list_for_cycle(cid)}
    assert set(runs) == set(ANALYSIS_AGENTS)  # still one row per agent

    news = runs["news"]
    assert news.outputs is None
    assert news.error is not None and "killed for the test" in news.error
    assert news.duration_ms is not None and news.duration_ms >= 0

    # the other four agents recorded a normal success row
    for name in ("portfolio", "stock", "market", "options"):
        assert runs[name].error is None
        assert isinstance(runs[name].outputs, dict)


def test_run_logging_is_optional(mock_llm, run_repo) -> None:
    before = run_repo.count()
    ctx = assemble_hedge_context(_inputs("cyc-runlog-none"), client=mock_llm)
    assert isinstance(ctx, HedgeContext)
    assert run_repo.count() == before  # nothing written when run_repo is omitted


def test_a_repository_failure_never_breaks_the_pass(mock_llm) -> None:
    class _BrokenSink:
        def create(self, record: Any) -> Any:
            raise RuntimeError("db is down")

        def finish(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover - never reached
            raise RuntimeError("db is down")

    ctx = assemble_hedge_context(
        _inputs("cyc-runlog-broken"), client=mock_llm, run_repo=_BrokenSink()
    )
    assert isinstance(ctx, HedgeContext)
    assert ctx.degraded_sections == []  # logging failure ≠ agent failure
