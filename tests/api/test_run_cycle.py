"""Tests for POST /run-cycle — task P6-BE-11 / issue #157.

Confirms:
- 202 with a schema-valid RunCycleOut body (cycle_id, status, started_at);
- a full cycle completes against stubbed externals and persists workflow_state;
- re-calling with the same engine sees the cycle in the DB.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.api.workflow import get_orchestrator_deps
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.workflow_repo import WorkflowRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# helpers / fakes
# ---------------------------------------------------------------------------


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
    """Echoes any submitted combo/single-leg payload back as fully filled."""

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = int(payload["qty"])
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:
            return {
                "id": "run-combo-1",
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
        return {
            "id": "run-single-1",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "qty": payload["qty"],
            "filled_qty": payload["qty"],
            "filled_avg_price": price.get(payload["side"], "2.00"),
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
        }


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client_and_engine(tmp_path: Path, analysis_inputs: Any) -> Iterator[tuple[TestClient, Any]]:
    """Migrated DB + TestClient wired with stubbed deps."""
    db_url = f"sqlite:///{tmp_path / 'run_cycle_test.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)

    import dataclasses

    from backend.agents.orchestrator.nodes import OrchestratorDeps

    stubbed_deps = OrchestratorDeps(
        inputs_provider=analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "SELECT_STRATEGY",
                "selected_strategy": "PUT_SPREAD",
                "rationale": "defined-risk downside protection",
                "confidence": 0.9,
                "verdict": "APPROVE",
            }
        ),
        broker=_FillingBroker(),
        engine=engine,
        preflight=False,
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    app.dependency_overrides[get_orchestrator_deps] = lambda: stubbed_deps

    with TestClient(app) as c:
        yield c, engine

    app.dependency_overrides.clear()
    engine.dispose()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_post_run_cycle_returns_202_with_cycle_id(client_and_engine: tuple) -> None:
    """POST /run-cycle responds 202 and the body is schema-valid."""
    client, _ = client_and_engine
    res = client.post("/run-cycle")
    assert res.status_code == 202, res.text
    data = res.json()
    assert "cycle_id" in data
    assert data["cycle_id"].startswith("cyc_")
    assert data["status"] == "started"
    assert "started_at" in data
    assert "message" in data


def test_post_run_cycle_cycle_id_is_present_in_db(client_and_engine: tuple) -> None:
    """After POST /run-cycle the cycle appears in workflow_state immediately."""
    client, engine = client_and_engine
    res = client.post("/run-cycle")
    assert res.status_code == 202
    cycle_id = res.json()["cycle_id"]

    repo = WorkflowRepository(engine)
    state = repo.get_state(cycle_id)
    # The endpoint stamps INITIAL/RUNNING before the background thread starts
    assert state is not None
    assert state.cycle_id == cycle_id


def test_post_run_cycle_full_cycle_completes_against_stubs(
    client_and_engine: tuple,
) -> None:
    """A complete cycle runs end-to-end with stubbed externals and persists state."""
    import time

    client, engine = client_and_engine
    res = client.post("/run-cycle")
    assert res.status_code == 202
    cycle_id = res.json()["cycle_id"]

    repo = WorkflowRepository(engine)

    # Wait for the background thread to finish (up to 30 s)
    deadline = time.time() + 30
    while time.time() < deadline:
        state = repo.get_state(cycle_id)
        if state and state.current_node == "MONITORING":
            break
        time.sleep(0.2)
    else:
        state = repo.get_state(cycle_id)
        pytest.fail(
            f"Cycle did not reach MONITORING within 30 s; last state: {state}"
        )

    transitions = repo.get_transitions(cycle_id)
    visited = [t.to_node for t in transitions]
    # All six pipeline nodes should appear at least once
    for node in ("INITIAL", "ANALYZING", "STRATEGY_EVALUATION", "RISK_CHECK", "EXECUTION", "MONITORING"):
        assert node in visited, f"Expected {node} in visited nodes; got {visited}"


def test_force_flag_is_accepted(client_and_engine: tuple) -> None:
    """POST /run-cycle with force=true is accepted (schema validation)."""
    client, _ = client_and_engine
    res = client.post("/run-cycle", json={"force": True})
    assert res.status_code == 202
    assert res.json()["cycle_id"].startswith("cyc_")
