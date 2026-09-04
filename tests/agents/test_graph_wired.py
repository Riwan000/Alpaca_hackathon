"""The orchestrator graph wired with real node bodies — P6-BE-2 … P6-BE-6.

``build_state_graph(OrchestratorDeps())`` must still compile with **no branches**
— P6-BE-7 remains the only task that can turn on conditional routing — and a
full ``invoke`` over the real chain (fake LLM + fake broker + a scratch DB) must
walk all six nodes once and leave every phase contract on the final state.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator import (
    GRAPH_NODES,
    OrchestratorDeps,
    build_orchestrator_graph,
    build_state_graph,
)
from backend.models.enums import ExecutionStatus
from backend.models.execution import ExecutionResult
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState
from backend.models.risk import RiskDecision
from backend.models.strategy import StrategyDecision

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()


def _inputs(_cycle_id: str | None) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": _cycle_id or "cyc-wired",
            "timestamp": _NOW.isoformat(),
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
                        },
                        {
                            "right": "PUT",
                            "strike": 135.0,
                            "expiration": _EXPIRY,
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


class _FillingBroker:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        base = int(payload["qty"])
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:  # multi-leg combo — a parent with a legs array
            return {
                "id": "wired-combo-1",
                "status": "filled",
                "submitted_at": "2026-09-03T14:35:00Z",
                "filled_at": "2026-09-03T14:35:02Z",
                "legs": [
                    {
                        "symbol": leg["symbol"],
                        "side": leg["side"],
                        "qty": str(int(leg["ratio_qty"]) * base),
                        "filled_qty": str(int(leg["ratio_qty"]) * base),
                        "filled_avg_price": price.get(leg["side"], "2.00"),
                        "status": "filled",
                        "filled_at": "2026-09-03T14:35:01Z",
                    }
                    for leg in payload["legs"]
                ],
            }
        # single-leg — a flat Alpaca order object, no nested legs
        return {
            "id": "wired-single-1",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "qty": payload["qty"],
            "filled_qty": payload["qty"],
            "filled_avg_price": price.get(payload["side"], "2.00"),
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
        }


def _fake_llm() -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    # One canned body serves both the manager and the risk agent: the manager
    # reads ``decision`` / ``selected_strategy``; the risk agent reads ``verdict``.
    fake.response_content = json.dumps(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PUT_SPREAD",
            "confidence": 0.9,
            "rationale": "defined-risk downside protection within budget",
            "verdict": "APPROVE",
        }
    )
    return fake


def test_deps_graph_still_has_no_conditional_branching() -> None:
    builder = build_state_graph(OrchestratorDeps())
    assert builder.branches == {}


def test_full_invoke_walks_every_node_and_fills_the_state(migrated_engine) -> None:
    deps = OrchestratorDeps(
        inputs_provider=_inputs,
        llm_client=_fake_llm(),
        broker=_FillingBroker(),
        engine=migrated_engine,
        preflight=False,
    )
    graph = build_orchestrator_graph(deps)

    final = graph.invoke({"cycle_id": "cyc-wired"})

    assert final["visited"] == list(GRAPH_NODES)
    assert final["current_node"] == "MONITORING"
    assert isinstance(final["hedge_context"], HedgeContext)
    assert isinstance(final["strategy_decision"], StrategyDecision)
    assert isinstance(final["risk_decision"], RiskDecision)
    assert isinstance(final["execution_result"], ExecutionResult)
    assert isinstance(final["monitoring_state"], MonitoringState)
    assert final["risk_decision"].verdict.value in ("APPROVE", "MODIFY")
    # the execution phase actually succeeded — not a silent FAILED
    assert final["execution_result"].status is not ExecutionStatus.FAILED
    assert not final.get("errors")  # additive reducer seeds [], nothing appended
