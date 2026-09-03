"""Tests for WorkflowRepository — task P6-DB-1, P6-DB-2."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.workflow_repo import WorkflowRepository
from backend.models.enums import WorkflowNode, WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture
def db_engine(tmp_path: Path):
    db_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test_wf.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed: {proc.stdout} {proc.stderr}"
    engine = create_engine(normalize_driver(db_url))
    try:
        yield engine
    finally:
        engine.dispose()


def test_workflow_repo_transitions_and_state(db_engine) -> None:
    repo = WorkflowRepository(db_engine)
    cycle_id = "cycle_test_wf_100"

    # Initial state
    state = repo.set_state(
        cycle_id=cycle_id,
        current_node=WorkflowNode.INITIAL,
        status=WorkflowStatus.RUNNING,
    )
    assert state.cycle_id == cycle_id
    assert state.current_node == "INITIAL"
    assert state.status == "RUNNING"

    # Advance to ANALYZING
    state2 = repo.set_state(
        cycle_id=cycle_id,
        current_node=WorkflowNode.ANALYZING,
        status=WorkflowStatus.RUNNING,
        detail={"source": "news_and_market"},
    )
    assert state2.current_node == "ANALYZING"

    # Advance to COMPLETED
    state3 = repo.set_state(
        cycle_id=cycle_id,
        current_node=WorkflowNode.COMPLETED,
        status=WorkflowStatus.COMPLETED,
    )
    assert state3.status == "COMPLETED"

    # Verify latest state
    latest = repo.get_state(cycle_id)
    assert latest is not None
    assert latest.current_node == "COMPLETED"
    assert latest.status == "COMPLETED"

    # Verify transitions history
    transitions = repo.get_transitions(cycle_id)
    assert len(transitions) == 3
    assert transitions[0].from_node is None
    assert transitions[0].to_node == "INITIAL"
    assert transitions[1].from_node == "INITIAL"
    assert transitions[1].to_node == "ANALYZING"
    assert transitions[2].from_node == "ANALYZING"
    assert transitions[2].to_node == "COMPLETED"
