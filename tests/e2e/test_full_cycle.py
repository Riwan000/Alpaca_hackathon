"""End-to-end tests for hands-off autonomous cycles — task P6-BE-13 / issue #159.

Covers:
1. `@pytest.mark.smoke` test against the live paper account + LLM:
   - triggers ``POST /run-cycle`` with no human input;
   - verifies node traversal through to ``MONITORING``;
   - confirms full auditable trail persisted across DB repositories
     (workflow transitions, agent runs, hypotheses, decisions, risk checks, orders/fills, monitoring state).
2. Deterministic E2E integration tests:
   - Full cycle with paper trade execution (APPROVE -> 6 nodes visited -> order filled & persisted).
   - Full cycle with justified NO_TRADE (skips RISK_CHECK and EXECUTION -> 0 orders -> monitoring state).
   - Full cycle with risk REJECT (skips EXECUTION -> 0 orders -> REJECT verdict persisted -> monitoring state).
   - End-to-end readback via GET /cycle/{cycle_id}/state and GET /workflow-state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator.nodes import OrchestratorDeps
from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.api.workflow import get_orchestrator_deps
from backend.config import get_settings
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.agent_runs_repo import AgentRunRepository
from backend.db.monitoring_repo import MonitoringRepository
from backend.db.orders_repo import OrderRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.db.strategy_repo import (
    StrategyDecisionRepository,
    StrategyHypothesisRepository,
)
from backend.db.workflow_repo import WorkflowRepository
from backend.integrations.alpaca import resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()


# --------------------------------------------------------------------------- #
# helpers & fakes
# --------------------------------------------------------------------------- #


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


class _FillingBroker:
    """Mock broker that fills submitted orders immediately with truthful fills."""

    def __init__(self) -> None:
        self.submitted_payloads: list[dict[str, Any]] = []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.submitted_payloads.append(payload)
        base = int(payload.get("qty", 1))
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:
            return {
                "id": f"combo-{len(self.submitted_payloads)}",
                "status": "filled",
                "submitted_at": "2026-09-03T14:35:00Z",
                "filled_at": "2026-09-03T14:35:02Z",
                "legs": [
                    {
                        "symbol": leg["symbol"],
                        "side": leg["side"],
                        "qty": str(int(leg.get("ratio_qty", 1)) * base),
                        "filled_qty": str(int(leg.get("ratio_qty", 1)) * base),
                        "filled_avg_price": price.get(leg["side"], "2.00"),
                        "status": "filled",
                        "filled_at": "2026-09-03T14:35:01Z",
                    }
                    for leg in payload["legs"]
                ],
            }
        return {
            "id": f"single-{len(self.submitted_payloads)}",
            "symbol": payload.get("symbol", "SPY"),
            "side": payload.get("side", "buy"),
            "qty": str(payload.get("qty", "1")),
            "filled_qty": str(payload.get("qty", "1")),
            "filled_avg_price": price.get(payload.get("side", "buy"), "2.00"),
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
        }


def _make_analysis_inputs(cycle_id: str | None = None) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": cycle_id or "cyc-e2e",
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
                    {
                        "symbol": "AAPL",
                        "qty": 200.0,
                        "avg_price": 150.0,
                        "market_value": 30_000.0,
                    },
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
                    },
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



def _wait_for_completion(
    repo: WorkflowRepository, cycle_id: str, timeout_sec: float = 30.0
) -> Any:
    """Poll until the cycle's terminal MONITORING node has actually finished.

    ``workflow_state.current_node`` flips to ``"MONITORING"`` the instant its
    *ENTER* transition is recorded — before the node body (which now may run a
    P7-BE-5 reopen sub-pipeline, itself several agent calls deep) has done any
    work. Waiting on that alone races the node's own persistence (the ``GET
    /workflow-state/stream`` SSE endpoint gets this right already — it waits for
    the MONITORING *EXIT* transition, or a terminal node). Match that here:
    require ``detail.phase == "EXIT"`` too, so callers only ever see a state
    whose ``monitoring_state`` / order / hedge-change rows are already written.
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        state = repo.get_state(cycle_id)
        if (
            state
            and state.current_node == "MONITORING"
            and (state.detail or {}).get("phase") == "EXIT"
        ):
            return state
        time.sleep(0.1)
    state = repo.get_state(cycle_id)
    pytest.fail(
        f"Cycle {cycle_id} did not reach MONITORING within {timeout_sec}s; last state: {state}"
    )


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def migrated_e2e_engine(tmp_path: Path) -> Iterator[Engine]:
    db_url = f"sqlite:///{tmp_path / 'full_cycle_e2e.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    try:
        yield engine
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- #
# Smoke Test — Live Paper Account (P6-BE-13)
# --------------------------------------------------------------------------- #


@pytest.mark.smoke
def test_smoke_full_cycle_paper_account(migrated_e2e_engine: Engine) -> None:
    """`pytest -m smoke` — one hands-off cycle on the paper account.

    Triggers POST /run-cycle, verifies all traversed nodes run to completion
    without human input, and confirms a complete auditable trail in the DB.
    """
    settings = get_settings()
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError:
        pytest.skip("no Alpaca paper credentials configured")

    if not (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")):
        pytest.skip("no LLM API key configured for smoke test")

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: migrated_e2e_engine

    try:
        with TestClient(app) as client:
            res = client.post("/run-cycle", json={"force": True})
            assert res.status_code == 202, f"POST /run-cycle failed: {res.text}"
            data = res.json()
            cycle_id = data["cycle_id"]
            assert cycle_id.startswith("cyc_")
            assert data["status"] == "started"

            repo = WorkflowRepository(migrated_e2e_engine)
            final_state = _wait_for_completion(repo, cycle_id, timeout_sec=60.0)
            assert final_state is not None
            assert final_state.current_node == "MONITORING"

            # 1. Transitions trail
            transitions = repo.get_transitions(cycle_id)
            visited_nodes = [t.to_node for t in transitions]
            assert "INITIAL" in visited_nodes
            assert "ANALYZING" in visited_nodes
            assert "STRATEGY_EVALUATION" in visited_nodes
            assert "MONITORING" in visited_nodes

            # 2. Strategy decision persisted
            strat_repo = StrategyDecisionRepository(migrated_e2e_engine)
            decision = strat_repo.for_cycle(cycle_id)
            assert decision is not None

            # 3. If traded, risk and orders are recorded; if NO_TRADE/REJECT, no orders
            risk_repo = RiskCheckRepository(migrated_e2e_engine)
            order_repo = OrderRepository(migrated_e2e_engine)
            checks = risk_repo.list_for_cycle(cycle_id)
            orders = order_repo.list_for_cycle(cycle_id)

            if "EXECUTION" in visited_nodes:
                assert len(checks) >= 1
                assert checks[0].verdict in ("APPROVE", "MODIFY")
                assert len(orders) >= 1
            else:
                # Justified NO_TRADE or REJECT
                assert len(orders) == 0

            # 4. Monitoring state snapshot persisted
            mon_repo = MonitoringRepository(migrated_e2e_engine)
            mon_state = mon_repo.get_latest_state()
            assert mon_state is not None
            assert mon_state.cycle_id == cycle_id
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Integration E2E Tests (Deterministic / Hands-off Invariants)
# --------------------------------------------------------------------------- #


def test_full_cycle_executes_paper_trade_hands_off(migrated_e2e_engine: Engine) -> None:
    """One hands-off /run-cycle executes a hedge trade and records a complete trail.

    Pipeline path:
    INITIAL -> ANALYZING -> STRATEGY_EVALUATION -> RISK_CHECK -> EXECUTION -> MONITORING
    """
    broker = _FillingBroker()
    stubbed_deps = OrchestratorDeps(
        inputs_provider=_make_analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "SELECT_STRATEGY",
                "selected_strategy": "PUT_SPREAD",
                "rationale": "downtrend downside protection with defined risk",
                "confidence": 0.92,
                "verdict": "APPROVE",
            }
        ),
        broker=broker,
        engine=migrated_e2e_engine,
        preflight=False,
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: migrated_e2e_engine
    app.dependency_overrides[get_orchestrator_deps] = lambda: stubbed_deps

    try:
        with TestClient(app) as client:
            # 1. Trigger cycle hands-off
            res = client.post("/run-cycle")
            assert res.status_code == 202
            cycle_id = res.json()["cycle_id"]

            repo = WorkflowRepository(migrated_e2e_engine)
            final_state = _wait_for_completion(repo, cycle_id, timeout_sec=20.0)
            assert final_state.current_node == "MONITORING"

            # 2. Workflow transitions: all 6 nodes visited in exact order
            transitions = repo.get_transitions(cycle_id)
            expected_nodes = [
                "INITIAL",
                "ANALYZING",
                "STRATEGY_EVALUATION",
                "RISK_CHECK",
                "EXECUTION",
                "MONITORING",
            ]
            seen_nodes = [t.to_node for t in transitions if (t.detail or {}).get("phase") == "ENTER"]
            assert seen_nodes == expected_nodes

            # 3. Agent runs persisted (ANALYZING phase)
            agent_runs = AgentRunRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(agent_runs) >= 3  # stock, market, news agents
            agent_names = {r.agent_name for r in agent_runs}
            assert "market_data" in agent_names or "MarketAgent" in agent_names or len(agent_names) >= 2

            # 4. Strategy hypotheses persisted (STRATEGY_EVALUATION phase)
            hypotheses = StrategyHypothesisRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(hypotheses) >= 1
            strategy_types = {h.strategy_type for h in hypotheses}
            assert "PUT_SPREAD" in strategy_types

            # 5. Strategy decision persisted
            strat_decision = StrategyDecisionRepository(migrated_e2e_engine).for_cycle(cycle_id)
            assert strat_decision is not None
            assert strat_decision.action in ("NEW_HEDGE", "SELECT_STRATEGY")

            # 6. Risk check persisted (RISK_CHECK phase)
            risk_checks = RiskCheckRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(risk_checks) == 1
            assert risk_checks[0].verdict == "APPROVE"

            # 7. Order & fills persisted (EXECUTION phase)
            orders = OrderRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(orders) == 1
            assert orders[0].status == "FILLED"
            assert orders[0].id is not None
            assert len(broker.submitted_payloads) == 1

            fills = OrderRepository(migrated_e2e_engine).fills_for(orders[0].id)
            assert len(fills) >= 1

            # 8. Terminal monitoring state persisted (MONITORING phase)
            mon_state = MonitoringRepository(migrated_e2e_engine).get_latest_state()
            assert mon_state is not None
            assert mon_state.cycle_id == cycle_id
            assert mon_state.monitoring_status == "ACTIVE"
    finally:
        app.dependency_overrides.clear()


def test_full_cycle_justified_no_trade_hands_off(migrated_e2e_engine: Engine) -> None:
    """One hands-off /run-cycle with a NO_TRADE outcome skips execution safely.

    Pipeline path:
    INITIAL -> ANALYZING -> STRATEGY_EVALUATION -> MONITORING
    (skips RISK_CHECK and EXECUTION)
    """
    broker = _FillingBroker()
    stubbed_deps = OrchestratorDeps(
        inputs_provider=_make_analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "NO_TRADE",
                "selected_strategy": None,
                "rationale": "Portfolio exposure within safe limits; market volatility subdued",
                "confidence": 0.95,
            }
        ),
        broker=broker,
        engine=migrated_e2e_engine,
        preflight=False,
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: migrated_e2e_engine
    app.dependency_overrides[get_orchestrator_deps] = lambda: stubbed_deps

    try:
        with TestClient(app) as client:
            res = client.post("/run-cycle")
            assert res.status_code == 202
            cycle_id = res.json()["cycle_id"]

            repo = WorkflowRepository(migrated_e2e_engine)
            final_state = _wait_for_completion(repo, cycle_id, timeout_sec=20.0)
            assert final_state.current_node == "MONITORING"

            transitions = repo.get_transitions(cycle_id)
            entered_nodes = [t.to_node for t in transitions if (t.detail or {}).get("phase") == "ENTER"]
            assert entered_nodes == ["INITIAL", "ANALYZING", "STRATEGY_EVALUATION", "MONITORING"]
            assert "RISK_CHECK" not in entered_nodes
            assert "EXECUTION" not in entered_nodes

            # Decision is justified NO_TRADE
            strat_decision = StrategyDecisionRepository(migrated_e2e_engine).for_cycle(cycle_id)
            assert strat_decision is not None
            assert strat_decision.action in ("NO_HEDGE", "NO_TRADE")

            # Invariant: 0 risk checks and 0 broker orders submitted
            risk_checks = RiskCheckRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(risk_checks) == 0

            orders = OrderRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(orders) == 0
            assert len(broker.submitted_payloads) == 0

            # Monitoring state is still persisted
            mon_state = MonitoringRepository(migrated_e2e_engine).get_latest_state()
            assert mon_state is not None
            assert mon_state.cycle_id == cycle_id
    finally:
        app.dependency_overrides.clear()


def test_full_cycle_risk_reject_hands_off(migrated_e2e_engine: Engine) -> None:
    """One hands-off /run-cycle with a risk REJECT outcome halts before execution.

    Pipeline path:
    INITIAL -> ANALYZING -> STRATEGY_EVALUATION -> RISK_CHECK -> MONITORING
    (skips EXECUTION)
    """
    broker = _FillingBroker()
    stubbed_deps = OrchestratorDeps(
        inputs_provider=_make_analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "SELECT_STRATEGY",
                "selected_strategy": "PUT_SPREAD",
                "rationale": "downtrend hedge",
                "confidence": 0.85,
                "verdict": "REJECT",
                "reason": "Exceeds maximum allowable portfolio hedge budget",
            }
        ),
        broker=broker,
        engine=migrated_e2e_engine,
        preflight=False,
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: migrated_e2e_engine
    app.dependency_overrides[get_orchestrator_deps] = lambda: stubbed_deps

    try:
        with TestClient(app) as client:
            res = client.post("/run-cycle")
            assert res.status_code == 202
            cycle_id = res.json()["cycle_id"]

            repo = WorkflowRepository(migrated_e2e_engine)
            final_state = _wait_for_completion(repo, cycle_id, timeout_sec=20.0)
            assert final_state.current_node == "MONITORING"

            transitions = repo.get_transitions(cycle_id)
            entered_nodes = [t.to_node for t in transitions if (t.detail or {}).get("phase") == "ENTER"]
            assert entered_nodes == [
                "INITIAL",
                "ANALYZING",
                "STRATEGY_EVALUATION",
                "RISK_CHECK",
                "MONITORING",
            ]
            assert "EXECUTION" not in entered_nodes

            # Risk check is persisted with REJECT verdict
            risk_checks = RiskCheckRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(risk_checks) == 1
            assert risk_checks[0].verdict == "REJECT"

            # Invariant: 0 broker orders submitted
            orders = OrderRepository(migrated_e2e_engine).list_for_cycle(cycle_id)
            assert len(orders) == 0
            assert len(broker.submitted_payloads) == 0

            # Monitoring state is persisted
            mon_state = MonitoringRepository(migrated_e2e_engine).get_latest_state()
            assert mon_state is not None
            assert mon_state.cycle_id == cycle_id
    finally:
        app.dependency_overrides.clear()


def test_full_cycle_state_readback(migrated_e2e_engine: Engine) -> None:
    """GET /cycle/{cycle_id}/state and GET /workflow-state return complete trail."""
    broker = _FillingBroker()
    stubbed_deps = OrchestratorDeps(
        inputs_provider=_make_analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "SELECT_STRATEGY",
                "selected_strategy": "PUT_SPREAD",
                "rationale": "downside hedge",
                "confidence": 0.90,
                "verdict": "APPROVE",
            }
        ),
        broker=broker,
        engine=migrated_e2e_engine,
        preflight=False,
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: migrated_e2e_engine
    app.dependency_overrides[get_orchestrator_deps] = lambda: stubbed_deps

    try:
        with TestClient(app) as client:
            res = client.post("/run-cycle")
            assert res.status_code == 202
            cycle_id = res.json()["cycle_id"]

            repo = WorkflowRepository(migrated_e2e_engine)
            _wait_for_completion(repo, cycle_id, timeout_sec=20.0)

            # 1. GET /cycle/{cycle_id}/state
            res_cycle = client.get(f"/cycle/{cycle_id}/state")
            assert res_cycle.status_code == 200
            cycle_data = res_cycle.json()
            assert cycle_data["cycle_id"] == cycle_id
            assert cycle_data["current_node"] == "MONITORING"
            assert len(cycle_data["transitions"]) >= 6

            # 2. GET /workflow-state
            res_wf = client.get("/workflow-state", params={"cycle_id": cycle_id})
            assert res_wf.status_code == 200
            wf_data = res_wf.json()
            assert wf_data["cycle_id"] == cycle_id
            assert wf_data["current_node"] == "MONITORING"
    finally:
        app.dependency_overrides.clear()
