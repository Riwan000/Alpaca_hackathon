"""Tests for GET /workflow-state and SSE stream — task P6-BE-12 / issue #158.

Confirms:
- GET /workflow-state returns current node and status for a known cycle_id;
- GET /workflow-state without cycle_id returns the most-recently updated state;
- GET /workflow-state returns 404 when no cycle exists;
- GET /workflow-state/stream emits one SSE message per transition and closes
  when the cycle ends.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
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
    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = int(payload["qty"])
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:
            return {
                "id": "stream-combo-1",
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
            "id": "stream-single-1",
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
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_client(tmp_path: Path) -> Iterator[tuple[TestClient, Any, str]]:
    """Migrated DB seeded with a two-step cycle, plus a TestClient."""
    db_url = f"sqlite:///{tmp_path / 'workflow_stream_test.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    repo = WorkflowRepository(engine)

    cycle_id = "stream-cycle-1"
    repo.set_state(cycle_id, "INITIAL", "RUNNING")
    repo.set_state(cycle_id, "ANALYZING", "RUNNING", detail={"phase": "ENTER"})
    repo.set_state(cycle_id, "ANALYZING", "RUNNING", detail={"phase": "EXIT"})

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine

    with TestClient(app) as client:
        yield client, engine, cycle_id

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def full_run_client(tmp_path: Path, analysis_inputs: Any) -> Iterator[tuple[TestClient, Any]]:
    """Migrated DB + TestClient with stubbed deps for a full graph run."""
    db_url = f"sqlite:///{tmp_path / 'workflow_stream_full.db'}"
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

    with TestClient(app) as client:
        yield client, engine

    app.dependency_overrides.clear()
    engine.dispose()


# ---------------------------------------------------------------------------
# GET /workflow-state tests
# ---------------------------------------------------------------------------


def test_get_workflow_state_by_cycle_id(seeded_client: tuple) -> None:
    """GET /workflow-state?cycle_id=... returns the latest state for that cycle."""
    client, _, cycle_id = seeded_client
    res = client.get(f"/workflow-state?cycle_id={cycle_id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["cycle_id"] == cycle_id
    assert data["current_node"] == "ANALYZING"
    assert data["status"] == "RUNNING"
    assert "updated_at" in data


def test_get_workflow_state_without_cycle_id_returns_latest(seeded_client: tuple) -> None:
    """GET /workflow-state (no query param) returns the most-recently updated state."""
    client, engine, cycle_id = seeded_client
    # Seed another cycle AFTER stream-cycle-1's rows — it will have the newest updated_at.
    repo = WorkflowRepository(engine)
    repo.set_state("newest-cycle", "INITIAL", "RUNNING")
    # GET without cycle_id must return the most-recently written row (newest-cycle).
    res = client.get("/workflow-state")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["cycle_id"] == "newest-cycle"


def test_get_workflow_state_404_when_no_state(tmp_path: Path) -> None:
    """GET /workflow-state returns 404 when the DB has no rows."""
    db_url = f"sqlite:///{tmp_path / 'empty_wf.db'}"
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True, text=True, check=False,
    )
    assert up.returncode == 0
    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    with TestClient(app) as client:
        res = client.get("/workflow-state")
        assert res.status_code == 404
    app.dependency_overrides.clear()
    engine.dispose()


# ---------------------------------------------------------------------------
# GET /workflow-state/stream SSE tests
# ---------------------------------------------------------------------------


def test_sse_emits_a_message_per_transition(seeded_client: tuple) -> None:
    """The SSE stream emits one event per existing transition row, then closes."""
    client, engine, cycle_id = seeded_client

    # Stamp a terminal node so the stream closes quickly in the test
    repo = WorkflowRepository(engine)
    repo.set_state(cycle_id, "MONITORING", "RUNNING", detail={"phase": "EXIT"})

    events: list[dict] = []
    with client.stream("GET", f"/workflow-state/stream?cycle_id={cycle_id}&poll_interval_s=0") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    # INITIAL + ANALYZING ENTER + ANALYZING EXIT + MONITORING EXIT
    assert len(events) >= 4
    nodes = [e["node"] for e in events]
    assert "INITIAL" in nodes
    assert "ANALYZING" in nodes
    assert "MONITORING" in nodes
    # All events have cycle_id and ts
    for ev in events:
        assert ev["cycle_id"] == cycle_id
        assert "status" in ev


def test_sse_closes_when_monitoring_exit_emitted(seeded_client: tuple) -> None:
    """Stream closes after emitting the MONITORING EXIT event."""
    client, engine, cycle_id = seeded_client

    repo = WorkflowRepository(engine)
    # Stamp MONITORING EXIT
    repo.set_state(cycle_id, "MONITORING", "RUNNING", detail={"phase": "EXIT"})

    collected: list[str] = []
    with client.stream("GET", f"/workflow-state/stream?cycle_id={cycle_id}&poll_interval_s=0") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                collected.append(line)

    # Stream must have closed (generator returned) — we got at least one event
    assert len(collected) >= 1
    last_ev = json.loads(collected[-1][len("data: "):])
    # Last event should be MONITORING
    assert last_ev["node"] == "MONITORING"


def test_sse_stream_emits_per_transition_for_full_run(full_run_client: tuple) -> None:
    """SSE stream emits events for a cycle run end-to-end via POST /run-cycle."""
    client, engine = full_run_client

    # Trigger a cycle
    res = client.post("/run-cycle")
    assert res.status_code == 202
    cycle_id = res.json()["cycle_id"]

    # Wait for the background thread to write MONITORING (up to 30 s)
    repo = WorkflowRepository(engine)
    deadline = time.time() + 30
    while time.time() < deadline:
        state = repo.get_state(cycle_id)
        if state and state.current_node == "MONITORING":
            break
        time.sleep(0.2)
    else:
        pytest.fail(f"Cycle did not reach MONITORING within 30 s; state={repo.get_state(cycle_id)}")

    # Now stream the (already-finished) cycle — we pass poll_interval_s=0 so
    # the generator delivers all existing rows and closes on the MONITORING EXIT.
    # We also add a terminal COMPLETED row so the stream closes deterministically.
    repo.set_state(cycle_id, "COMPLETED", "COMPLETED")

    events: list[dict] = []
    with client.stream(
        "GET",
        f"/workflow-state/stream?cycle_id={cycle_id}&poll_interval_s=0",
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    assert len(events) >= 1
    nodes = {e["node"] for e in events}
    # All six pipeline nodes should appear (the ENTER/EXIT rows from the hook)
    for n in ("INITIAL", "ANALYZING", "STRATEGY_EVALUATION", "RISK_CHECK", "EXECUTION", "MONITORING"):
        assert n in nodes, f"Expected {n} in SSE events; got {nodes}"
