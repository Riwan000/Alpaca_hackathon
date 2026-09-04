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


def _D(value: str) -> decimal.Decimal:
    return decimal.Decimal(value)


def test_vs_benchmark(tmp_path: Path) -> None:
    """P8-BE-2: before any hedge hedged == unhedged; a protective put in a drop
    cushions the hedged drawdown below the unhedged benchmark (BRD §36)."""
    db_url = f"sqlite:///{tmp_path / 'benchmark_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    repo = PerformanceRepository(engine)

    # Two pre-hedge points: no hedge overlay, so net_pnl == benchmark_pnl.
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_0",
            portfolio_pnl=_D("0.0000"),
            hedge_pnl=_D("0.0000"),
            net_pnl=_D("0.0000"),
            drawdown=_D("0.0000"),
            hedge_cost=_D("0.0000"),
            benchmark_pnl=_D("0.0000"),
        )
    )
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_1",
            portfolio_pnl=_D("-5000.0000"),
            hedge_pnl=_D("0.0000"),
            net_pnl=_D("-5000.0000"),
            drawdown=_D("-0.0200"),
            hedge_cost=_D("0.0000"),
            benchmark_pnl=_D("-5000.0000"),
        )
    )
    # Protective put bought; market drops further — the put pays off, so the
    # hedged curve troughs at -6000 while the unhedged benchmark sinks to -12000.
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_2",
            portfolio_pnl=_D("-12000.0000"),
            hedge_pnl=_D("6000.0000"),
            net_pnl=_D("-6000.0000"),
            drawdown=_D("-0.0240"),
            hedge_cost=_D("800.0000"),
            benchmark_pnl=_D("-12000.0000"),
        )
    )
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_3",
            portfolio_pnl=_D("-3000.0000"),
            hedge_pnl=_D("4000.0000"),
            net_pnl=_D("1000.0000"),
            drawdown=_D("0.0000"),
            hedge_cost=_D("800.0000"),
            benchmark_pnl=_D("-3000.0000"),
        )
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/pnl/vs-benchmark")
            assert res.status_code == 200, res.text
            data = res.json()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    points = {p["cycle_id"]: p for p in data["points"]}
    assert set(points) == {"cycle_0", "cycle_1", "cycle_2", "cycle_3"}

    # Before any hedge, hedged tracks unhedged exactly.
    for cid in ("cycle_0", "cycle_1"):
        p = points[cid]
        assert p["hedged_pnl"] == p["unhedged_pnl"]
        assert p["hedge_cushion"] == 0.0
        assert p["hedged_drawdown"] == p["unhedged_drawdown"]

    # After the protective put, the hedged drawdown is cushioned below the benchmark.
    assert points["cycle_2"]["hedged_drawdown"] < points["cycle_2"]["unhedged_drawdown"]
    assert data["hedged_max_drawdown"] == 6000.0
    assert data["unhedged_max_drawdown"] == 12000.0
    assert data["hedged_max_drawdown"] < data["unhedged_max_drawdown"]
    assert data["drawdown_reduction"] == 6000.0
    assert data["is_cushioned"] is True
    assert data["hedge_cushion"] == 4000.0
    assert data["hedge_cost"] == 1600.0


def test_vs_benchmark_empty_db(tmp_path: Path) -> None:
    """No performance rows yet → a well-formed, zeroed comparison, not a 500."""
    db_url = f"sqlite:///{tmp_path / 'benchmark_empty_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            data = test_client.get("/pnl/vs-benchmark").json()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert data["points"] == []
    assert data["hedged_max_drawdown"] == 0.0
    assert data["unhedged_max_drawdown"] == 0.0
    assert data["is_cushioned"] is True
