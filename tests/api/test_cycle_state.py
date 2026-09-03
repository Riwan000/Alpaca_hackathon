"""Tests for GET /cycle/:id/state endpoint — task P6-DB-3."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.workflow_repo import WorkflowRepository
from backend.models.enums import WorkflowNode, WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_url = f"sqlite:///{tmp_path / 'workflow_readback_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    wf_repo = WorkflowRepository(engine)

    # Seed cycle_1 with 2 transitions
    wf_repo.set_state("cycle_1", WorkflowNode.INITIAL, WorkflowStatus.RUNNING)
    wf_repo.set_state(
        "cycle_1",
        WorkflowNode.ANALYZING,
        WorkflowStatus.RUNNING,
        detail={"agent": "market"},
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_get_cycle_state_success(client: TestClient) -> None:
    res = client.get("/cycle/cycle_1/state")
    assert res.status_code == 200
    data = res.json()
    assert data["cycle_id"] == "cycle_1"
    assert data["current_node"] == "ANALYZING"
    assert data["status"] == "RUNNING"
    assert len(data["transitions"]) == 2
    assert data["transitions"][0]["to_node"] == "INITIAL"
    assert data["transitions"][1]["to_node"] == "ANALYZING"
    assert data["transitions"][1]["detail"] == {"agent": "market"}


def test_get_cycle_state_not_found(client: TestClient) -> None:
    res = client.get("/cycle/unknown_cycle/state")
    assert res.status_code == 404
