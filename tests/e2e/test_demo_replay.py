"""Tests for demo narrative replay script — task P8-BE-6."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.monitoring_repo import MonitoringRepository
from backend.db.orders_repo import OrderRepository
from backend.db.performance_repo import PerformanceRepository
from backend.db.repository import PortfolioSnapshotRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.db.strategy_repo import StrategyDecisionRepository
from backend.db.workflow_repo import WorkflowRepository
from backend.demo_replay import replay_demo_narrative

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


def test_demo_replay_full_narrative(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'demo_replay.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed: {proc.stdout} {proc.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    try:
        cycle_id = "test_demo_cycle_1"
        res = replay_demo_narrative(engine, cycle_id=cycle_id)
        assert res["status"] == "completed"

        # Verify portfolio snapshot & positions
        snap_repo = PortfolioSnapshotRepository(engine)
        latest_snap = snap_repo.latest()
        assert latest_snap is not None
        assert latest_snap.cycle_id == cycle_id

        # Verify strategy decision
        dec_repo = StrategyDecisionRepository(engine)
        dec = dec_repo.for_cycle(cycle_id)
        assert dec is not None
        assert dec.action == "NEW_HEDGE"
        assert dec.selected_hypothesis_id is not None

        # Verify risk check
        risk_repo = RiskCheckRepository(engine)
        checks = risk_repo.list_for_cycle(cycle_id)
        assert len(checks) >= 1
        assert checks[0].verdict == "APPROVE"

        # Verify order and fill
        order_repo = OrderRepository(engine)
        orders = order_repo.list_for_cycle(cycle_id)
        assert len(orders) == 1
        assert orders[0].status == "FILLED"
        fills = order_repo.fills_for(orders[0].id)
        assert len(fills) == 1
        assert fills[0].leg_symbol == "SPY261218P00500000"

        # Verify monitoring & reassessment event
        mon_repo = MonitoringRepository(engine)
        reassessments = mon_repo.list_reassessments(cycle_id)
        assert len(reassessments) == 1
        assert reassessments[0].outcome == "DECREASE"

        changes = mon_repo.list_hedge_changes(cycle_id)
        assert len(changes) == 1
        assert changes[0].delta == -0.5

        # Verify performance series
        perf_repo = PerformanceRepository(engine)
        series = perf_repo.get_series(cycle_id)
        assert len(series) == 2

        # Verify workflow transitions
        wf_repo = WorkflowRepository(engine)
        wf_state = wf_repo.get_state(cycle_id)
        assert wf_state is not None
        assert wf_state.status == "COMPLETED"
    finally:
        engine.dispose()
