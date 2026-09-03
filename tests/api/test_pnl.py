"""Tests for P&L endpoints — task P8-BE-1, P8-BE-2."""

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
from backend.db.performance_repo import PerformanceRecord, PerformanceRepository

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
    db_url = f"sqlite:///{tmp_path / 'pnl_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    repo = PerformanceRepository(engine)

    repo.save(
        PerformanceRecord(
            cycle_id="cycle_p1",
            portfolio_pnl=decimal.Decimal("-2000.0000"),
            hedge_pnl=decimal.Decimal("1500.0000"),
            net_pnl=decimal.Decimal("-500.0000"),
            drawdown=decimal.Decimal("-0.0050"),
            hedge_cost=decimal.Decimal("200.0000"),
            benchmark_pnl=decimal.Decimal("-2000.0000"),
        )
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_get_current_pnl(client: TestClient) -> None:
    res = client.get("/pnl/current")
    assert res.status_code == 200
    data = res.json()
    assert data["cycle_id"] == "cycle_p1"
    assert data["portfolio_pnl"] == -2000.0
    assert data["hedge_pnl"] == 1500.0
    assert data["net_pnl"] == -500.0


def test_get_pnl_series(client: TestClient) -> None:
    res = client.get("/pnl/series")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["cycle_id"] == "cycle_p1"
    assert data[0]["net_pnl"] == -500.0
