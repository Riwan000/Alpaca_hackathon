"""Tests for monitoring repository — tasks P7-DB-1, P7-DB-2, P7-DB-3, P7-DB-4."""

from __future__ import annotations

import datetime as _dt
import decimal
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.monitoring_repo import (
    HedgeChangeRecord,
    MonitoringEventRecord,
    MonitoringRepository,
    MonitoringStateRecord,
    ReassessmentEventRecord,
)
from backend.models.enums import HedgeAction, TriggerType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture
def db_engine(tmp_path: Path):
    db_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test_monitoring.db'}"
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


def test_monitoring_events(db_engine) -> None:
    """Task P7-DB-1: Level-1 monitoring check writes an event row."""
    repo = MonitoringRepository(db_engine)
    event = repo.record_event(
        MonitoringEventRecord(
            cycle_id="cycle_m_1",
            trigger_type=TriggerType.VOLATILITY_SPIKE,
            observed={"iv_spike": 0.35},
            threshold=decimal.Decimal("0.2500"),
        )
    )
    assert event.id is not None
    assert event.trigger_type == "VOLATILITY_SPIKE"

    events = repo.list_events(cycle_id="cycle_m_1")
    assert len(events) == 1
    assert events[0].observed == {"iv_spike": 0.35}


def test_reassessment(db_engine) -> None:
    """Task P7-DB-2: Level-2 run links trigger and stores outcome enum."""
    repo = MonitoringRepository(db_engine)
    event = repo.record_event(
        MonitoringEventRecord(
            cycle_id="cycle_m_2",
            trigger_type=TriggerType.DRAWDOWN_LIMIT,
            threshold=decimal.Decimal("0.0500"),
        )
    )

    reassessment = repo.record_reassessment(
        ReassessmentEventRecord(
            cycle_id="cycle_m_2",
            trigger_event_id=event.id,
            outcome=HedgeAction.DECREASE,
            reason="Market stabilization detected, reducing hedge by 50%",
            context={"portfolio_drift": -0.04},
        )
    )
    assert reassessment.id is not None
    assert reassessment.outcome == "DECREASE"

    history = repo.list_reassessments(cycle_id="cycle_m_2")
    assert len(history) == 1
    assert history[0].trigger_event_id == event.id
    assert history[0].outcome == "DECREASE"


def test_hedge_changes(db_engine) -> None:
    """Task P7-DB-3: hedge adjustment writes before/after ratio, delta, reason."""
    repo = MonitoringRepository(db_engine)
    change = repo.record_hedge_change(
        HedgeChangeRecord(
            cycle_id="cycle_m_3",
            before_hedge_ratio=decimal.Decimal("1.0000"),
            after_hedge_ratio=decimal.Decimal("0.5000"),
            delta=decimal.Decimal("-0.5000"),
            action=HedgeAction.DECREASE,
            reason="Market stabilized",
        )
    )
    assert change.id is not None
    assert change.delta == decimal.Decimal("-0.5000")

    changes = repo.list_hedge_changes(cycle_id="cycle_m_3")
    assert len(changes) == 1
    assert changes[0].before_hedge_ratio == decimal.Decimal("1.0000")
    assert changes[0].after_hedge_ratio == decimal.Decimal("0.5000")


def test_state(db_engine) -> None:
    """Task P7-DB-4: MonitoringState round-trips with nullable cooldown & trigger history."""
    repo = MonitoringRepository(db_engine)
    cooldown = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=30)
    saved = repo.save_state(
        MonitoringStateRecord(
            cycle_id="cycle_m_4",
            current_hedge=decimal.Decimal("0.7500"),
            target_hedge=decimal.Decimal("0.8000"),
            cooldown_until=cooldown,
            trigger_history=[{"trigger": "VOLATILITY_SPIKE", "ts": "2026-09-04T00:00:00Z"}],
            monitoring_status="COOLDOWN",
        )
    )
    assert saved.id is not None

    latest = repo.get_latest_state()
    assert latest is not None
    assert latest.current_hedge == decimal.Decimal("0.7500")
    assert latest.target_hedge == decimal.Decimal("0.8000")
    assert latest.monitoring_status == "COOLDOWN"
    assert len(latest.trigger_history) == 1
