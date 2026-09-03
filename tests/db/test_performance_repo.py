"""Tests for PerformanceRepository — tasks P8-DB-1, P8-DB-2, P8-DB-3."""

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
from backend.db.performance_repo import PerformanceRecord, PerformanceRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture
def db_engine(tmp_path: Path):
    db_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test_perf.db'}"
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


def test_performance_identity(db_engine) -> None:
    """Task P8-DB-1: net_pnl = portfolio_pnl + hedge_pnl identity holds."""
    repo = PerformanceRepository(db_engine)
    now = _dt.datetime.now(_dt.timezone.utc)

    # Valid identity row
    saved = repo.save(
        PerformanceRecord(
            cycle_id="cycle_p1",
            portfolio_pnl=decimal.Decimal("-5000.0000"),
            hedge_pnl=decimal.Decimal("3200.0000"),
            net_pnl=decimal.Decimal("-1800.0000"),
            drawdown=decimal.Decimal("-0.0180"),
            hedge_cost=decimal.Decimal("450.0000"),
            benchmark_pnl=decimal.Decimal("-5000.0000"),
            ts=now,
        )
    )
    assert saved.id is not None
    assert saved.net_pnl == decimal.Decimal("-1800.0000")

    # Invalid identity raises ValueError
    with pytest.raises(ValueError, match="Identity net_pnl"):
        repo.save(
            PerformanceRecord(
                cycle_id="cycle_bad",
                portfolio_pnl=decimal.Decimal("1000.0000"),
                hedge_pnl=decimal.Decimal("500.0000"),
                net_pnl=decimal.Decimal("2000.0000"),  # Bad sum
                drawdown=decimal.Decimal("0.0000"),
                hedge_cost=decimal.Decimal("0.0000"),
                benchmark_pnl=decimal.Decimal("1000.0000"),
            )
        )


def test_benchmark(db_engine) -> None:
    """Task P8-DB-2: Store unhedged benchmark series and assert divergence on hedge."""
    repo = PerformanceRepository(db_engine)
    t1 = _dt.datetime.now(_dt.timezone.utc)
    t2 = t1 + _dt.timedelta(hours=1)

    # Unhedged point: net_pnl == benchmark_pnl
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_b1",
            portfolio_pnl=decimal.Decimal("0.0000"),
            hedge_pnl=decimal.Decimal("0.0000"),
            net_pnl=decimal.Decimal("0.0000"),
            drawdown=decimal.Decimal("0.0000"),
            hedge_cost=decimal.Decimal("0.0000"),
            benchmark_pnl=decimal.Decimal("0.0000"),
            ts=t1,
        )
    )

    # Hedged point: hedge cushions portfolio loss
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_b2",
            portfolio_pnl=decimal.Decimal("-10000.0000"),
            hedge_pnl=decimal.Decimal("7000.0000"),
            net_pnl=decimal.Decimal("-3000.0000"),
            drawdown=decimal.Decimal("-0.0300"),
            hedge_cost=decimal.Decimal("800.0000"),
            benchmark_pnl=decimal.Decimal("-10000.0000"),
            ts=t2,
        )
    )

    series = repo.get_benchmark_series()
    assert len(series) == 2
    # Point 1: no cushion
    assert series[0]["hedge_cushion"] == 0.0
    # Point 2: cushion = -3000 - (-10000) = +7000
    assert series[1]["hedge_cushion"] == 7000.0


def test_dashboard_query_plan(db_engine) -> None:
    """Task P8-DB-3: dashboard index query plan confirmation."""
    repo = PerformanceRepository(db_engine)
    plan = repo.explain_dashboard_query()
    assert plan is not None
