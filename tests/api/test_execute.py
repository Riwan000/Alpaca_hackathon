"""``POST /execute`` integration tests — task P5-BE-15 / issue #138.

Confirms:
- 200 with a schema-valid :class:`~backend.models.execution.ExecutionResult`;
- the happy path persists a ``risk_checks`` row, one ``orders`` row and one
  ``fills`` row per filled leg;
- a pre-flight abort returns a truthful ``FAILED`` result with **no order sent**
  (an ``execution_failures`` row is written instead);
- a non-approved decision is rejected with 422.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.execute import get_execution_broker
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.execution_failures_repo import ExecutionFailureRepository
from backend.db.orders_repo import OrderRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.models.execution import ExecutionResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration

_CYCLE = "cyc-execute"
_LONG = "AAPL261003P00145000"
_SHORT = "AAPL261003P00140000"


# --------------------------------------------------------------------------- #
# fakes / builders
# --------------------------------------------------------------------------- #


class _FillingBroker:
    """Echoes the submitted mleg payload back as a fully-filled combo order."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        base = int(payload["qty"])
        fill_price = {"buy": "3.20", "sell": "1.90"}
        legs = [
            {
                "symbol": leg["symbol"],
                "side": leg["side"],
                "qty": str(int(leg["ratio_qty"]) * base),
                "filled_qty": str(int(leg["ratio_qty"]) * base),
                "filled_avg_price": fill_price[leg["side"]],
                "status": "filled",
                "filled_at": "2026-09-03T14:35:01Z",
            }
            for leg in payload["legs"]
        ]
        return {
            "id": "combo-exec-1",
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
            "legs": legs,
        }


def _hypothesis() -> dict[str, Any]:
    return {
        "cycle_id": _CYCLE,
        "strategy": "PUT_SPREAD",
        "action": "NEW_HEDGE",
        "viable": True,
        "legs": [
            {
                "underlying": "AAPL",
                "right": "PUT",
                "side": "BUY",
                "strike": 145.0,
                "expiration": "2026-10-03",
                "quantity": 2,
                "limit_price": 3.15,
            },
            {
                "underlying": "AAPL",
                "right": "PUT",
                "side": "SELL",
                "strike": 140.0,
                "expiration": "2026-10-03",
                "quantity": 2,
                "limit_price": 1.95,
            },
        ],
        "cost": 240.0,
        "rationale": "defined-risk downside protection",
    }


def _decision(verdict: str = "APPROVE", **overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "cycle_id": _CYCLE,
        "verdict": verdict,
        "rationale": "risk gate cleared the plan",
        "approved_hypothesis": _hypothesis(),
    }
    raw.update(overrides)
    return raw


def _context(*, timestamp: str | None = None) -> dict[str, Any]:
    return {
        "cycle_id": _CYCLE,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "portfolio_state": {
            "total_value": 145_000.0,
            "cash": 100_000.0,
            "equity": 45_000.0,
            "buying_power": 50_000.0,
            "positions": [],
        },
        "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
        "option_candidates": [
            {
                "underlying": "AAPL",
                "right": "PUT",
                "strike": 145.0,
                "expiration": "2026-10-03",
                "premium": 3.15,
                "bid": 3.1,
                "ask": 3.2,
                "open_interest": 4200,
            },
            {
                "underlying": "AAPL",
                "right": "PUT",
                "strike": 140.0,
                "expiration": "2026-10-03",
                "premium": 1.95,
                "bid": 1.9,
                "ask": 2.0,
                "open_interest": 3100,
            },
        ],
    }


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def _engine(tmp_path: Path) -> Iterator[Any]:
    db_url = f"sqlite:///{tmp_path / 'execute_scratch.db'}"
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def client(_engine: Any) -> Iterator[TestClient]:
    broker = _FillingBroker()
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: _engine
    app.dependency_overrides[get_execution_broker] = lambda: broker
    try:
        with TestClient(app) as tc:
            tc.broker = broker  # type: ignore[attr-defined]
            yield tc
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #


def test_execute_returns_200_and_valid_execution_result(client: TestClient) -> None:
    response = client.post(
        "/execute", json={"decision": _decision(), "context": _context()}
    )
    assert response.status_code == 200, response.text

    result = ExecutionResult.model_validate(response.json())
    assert result.cycle_id == _CYCLE
    assert result.status.value == "FILLED"
    assert {fl.leg_symbol for fl in result.filled_legs} == {_LONG, _SHORT}


def test_execute_persists_risk_check_order_and_fills(
    client: TestClient, _engine: Any
) -> None:
    response = client.post(
        "/execute", json={"decision": _decision(), "context": _context()}
    )
    assert response.status_code == 200, response.text

    risk = RiskCheckRepository(_engine).for_cycle(_CYCLE)
    assert risk is not None and risk.verdict == "APPROVE"

    orders = OrderRepository(_engine)
    rows = orders.list_for_cycle(_CYCLE)
    assert len(rows) == 1
    assert rows[0].status == "FILLED"
    assert rows[0].broker_order_id == "combo-exec-1"
    assert orders.count_fills() == 2


def test_execute_applies_modify_before_submitting(client: TestClient, _engine: Any) -> None:
    decision = _decision(
        verdict="MODIFY",
        modifications=[
            {"field": "quantity", "from_value": 2, "to_value": 1, "reason": "cap size"}
        ],
    )
    response = client.post("/execute", json={"decision": decision, "context": _context()})
    assert response.status_code == 200, response.text

    result = ExecutionResult.model_validate(response.json())
    assert all(fl.qty == 1 for fl in result.filled_legs)
    # the submitted combo carried the reduced size
    assert client.broker.payloads[0]["qty"] == "1"  # type: ignore[attr-defined]


def test_execute_preflight_abort_sends_no_order(client: TestClient, _engine: Any) -> None:
    stale = _context(timestamp="2026-09-03T14:30:00Z")
    response = client.post("/execute", json={"decision": _decision(), "context": stale})

    assert response.status_code == 200, response.text
    result = ExecutionResult.model_validate(response.json())
    assert result.status.value == "FAILED"
    assert "pre-flight abort" in (result.error or "")

    assert OrderRepository(_engine).count() == 0
    failures = ExecutionFailureRepository(_engine).list_for_cycle(_CYCLE)
    assert failures and failures[0].stage == "PREFLIGHT"
    # the risk evaluation is still recorded
    assert RiskCheckRepository(_engine).for_cycle(_CYCLE) is not None
    # nothing was sent to the broker
    assert client.broker.payloads == []  # type: ignore[attr-defined]


def test_execute_rejects_a_non_approved_decision(client: TestClient) -> None:
    rejected = _decision(
        verdict="REJECT", violations=["cost over budget"], approved_hypothesis=None
    )
    response = client.post("/execute", json={"decision": rejected, "context": _context()})
    assert response.status_code == 422
