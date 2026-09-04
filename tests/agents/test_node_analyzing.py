"""``ANALYZING`` node — task P6-BE-2 / issue #148.

Confirms the node wraps the Phase 3 chain:
- a healthy run puts a schema-valid :class:`HedgeContext` on the state and does
  not flag ``degraded``;
- one analysis agent failing still yields a context, with ``degraded=True`` and
  the section named in ``notes`` (BRD §31);
- a *hard* failure (the inputs provider raising) leaves no context but does not
  crash — it records an ``errors`` entry and routes to ``MONITORING``;
- the node keeps the state's ``cycle_id`` authoritative over the inputs bundle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.agents.assembler import ANALYSIS_AGENT_FNS
from backend.agents.base import AgentError
from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator.nodes import OrchestratorDeps, analyzing_node
from backend.models.hedge_context import HedgeContext

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()


def _inputs(cycle_id: str = "cyc-node-analyzing") -> AnalysisInputs:
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
                "index_price": 498.2,
                "vix": 24.5,
                "sector_trends": {"tech": "DOWN"},
                "macro_notes": ["Fed on hold"],
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


def _run(node: Any, state: dict[str, Any]) -> dict[str, Any]:
    return node(state)


def test_healthy_run_puts_a_valid_hedge_context_on_the_state(mock_llm) -> None:
    node = analyzing_node(
        OrchestratorDeps(inputs_provider=lambda _cid: _inputs("cyc-x"), llm_client=mock_llm)
    )

    out = _run(node, {"cycle_id": "cyc-x"})

    ctx = out["hedge_context"]
    assert isinstance(ctx, HedgeContext)
    HedgeContext.model_validate(ctx.model_dump())
    assert ctx.degraded_sections == []
    assert out["current_node"] == "ANALYZING"
    assert out["visited"] == ["ANALYZING"]
    assert not out.get("degraded")
    assert "errors" not in out


def test_one_agent_failure_sets_degraded_but_still_returns_a_context(mock_llm) -> None:
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise AgentError("killed for the test")

    node = analyzing_node(
        OrchestratorDeps(
            inputs_provider=lambda _cid: _inputs(),
            llm_client=mock_llm,
            agent_fns={**ANALYSIS_AGENT_FNS, "news": _boom},
        )
    )

    out = _run(node, {"cycle_id": "cyc-node-analyzing"})

    ctx = out["hedge_context"]
    assert isinstance(ctx, HedgeContext)
    assert ctx.degraded_sections == ["news_context"]
    assert out["degraded"] is True
    assert any("news_context" in note for note in out["notes"])


def test_hard_failure_records_an_error_and_routes_to_monitoring() -> None:
    def _explode(_cid: str | None) -> AnalysisInputs:
        raise RuntimeError("inputs backend down")

    node = analyzing_node(OrchestratorDeps(inputs_provider=_explode))

    out = _run(node, {"cycle_id": "cyc-x"})

    assert "hedge_context" not in out
    assert out["route"] == "MONITORING"
    assert any("ANALYZING" in e for e in out["errors"])
    assert out["current_node"] == "ANALYZING"


def test_state_cycle_id_wins_over_the_inputs_bundle(mock_llm) -> None:
    node = analyzing_node(
        OrchestratorDeps(
            inputs_provider=lambda _cid: _inputs("stale-cycle-id"), llm_client=mock_llm
        )
    )

    out = _run(node, {"cycle_id": "authoritative-cycle"})

    assert out["hedge_context"].cycle_id == "authoritative-cycle"
    assert out["cycle_id"] == "authoritative-cycle"
