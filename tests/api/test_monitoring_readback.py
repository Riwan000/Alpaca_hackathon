"""Tests for monitoring read-back endpoints — task P7-DB-5."""

from __future__ import annotations

import decimal
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
from backend.db.monitoring_repo import (
    MonitoringEventRecord,
    MonitoringRepository,
    MonitoringStateRecord,
)
from backend.models.enums import TriggerType

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
    db_url = f"sqlite:///{tmp_path / 'monitoring_readback_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    repo = MonitoringRepository(engine)

    repo.save_state(
        MonitoringStateRecord(
            cycle_id="cycle_mon_1",
            current_hedge=decimal.Decimal("0.8500"),
            target_hedge=decimal.Decimal("0.9000"),
            trigger_history=[{"type": "VOLATILITY_SPIKE"}],
            monitoring_status="ACTIVE",
        )
    )

    repo.record_event(
        MonitoringEventRecord(
            cycle_id="cycle_mon_1",
            trigger_type=TriggerType.VOLATILITY_SPIKE,
            observed={"iv": 0.42},
            threshold=decimal.Decimal("0.3000"),
        )
    )

    repo.record_event(
        MonitoringEventRecord(
            cycle_id="cycle_mon_2",
            trigger_type=TriggerType.MANUAL,
            observed={"caller": "user"},
        )
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_get_monitoring_state(client: TestClient) -> None:
    res = client.get("/monitoring/state")
    assert res.status_code == 200
    data = res.json()
    assert data["current_hedge"] == 0.85
    assert data["target_hedge"] == 0.90
    assert data["monitoring_status"] == "ACTIVE"
    assert len(data["trigger_history"]) == 1


def test_list_monitoring_events(client: TestClient) -> None:
    res_all = client.get("/monitoring/events")
    assert res_all.status_code == 200
    events_all = res_all.json()
    assert len(events_all) == 2

    res_filtered = client.get("/monitoring/events?cycle_id=cycle_mon_1")
    assert res_filtered.status_code == 200
    events_filtered = res_filtered.json()
    assert len(events_filtered) == 1
    assert events_filtered[0]["trigger_type"] == "VOLATILITY_SPIKE"
    assert events_filtered[0]["threshold"] == 0.30
