"""Integration test: computed portfolio metrics persist through the repository layer — task P2-DB-1.

Flow: aggregate positions into a metric set (stand-in for the P2-BE quant
engine), ``PortfolioSnapshotRepository.save`` it, read it back and assert every
metric is unchanged, and confirm a row physically lands in
``portfolio_snapshots``.
"""

from __future__ import annotations

import datetime
import decimal
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.repository import PortfolioSnapshotRecord, PortfolioSnapshotRepository
from backend.db.seed import DEMO_POSITIONS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'metrics_scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _aggregate_snapshot(
    cycle_id: str,
    ts: datetime.datetime,
    cash: decimal.Decimal,
    buying_power: decimal.Decimal,
    positions: list[dict],
) -> PortfolioSnapshotRecord:
    """Minimal stand-in for the P2-BE quant engine.

    equity = Σ position market value; total_value = cash + equity.
    """
    equity = sum((p["market_value"] for p in positions), decimal.Decimal("0"))
    return PortfolioSnapshotRecord(
        cycle_id=cycle_id,
        total_value=cash + equity,
        cash=cash,
        equity=equity,
        buying_power=buying_power,
        ts=ts,
    )


def test_metrics_persist_round_trip(tmp_path: Path) -> None:
    """Task P2-DB-1: compute → repo.save → read back equal; a row appears in portfolio_snapshots."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        # 1. compute
        computed = _aggregate_snapshot(
            cycle_id="cycle_metrics_persist_001",
            ts=datetime.datetime(2026, 9, 3, 15, 30, tzinfo=datetime.timezone.utc),
            cash=decimal.Decimal("25000.0000"),
            buying_power=decimal.Decimal("50000.0000"),
            positions=DEMO_POSITIONS,
        )
        assert computed.id is None
        # 22500 + 18000 + 20500 + 14000 held in the demo portfolio
        assert computed.equity == decimal.Decimal("75000.0000")
        assert computed.total_value == decimal.Decimal("100000.0000")

        # 2. repo.save
        repo = PortfolioSnapshotRepository(engine)
        saved = repo.save(computed)
        assert saved.id is not None

        # 3. read back equal
        fetched = repo.get(saved.id)
        assert fetched is not None
        assert fetched == saved
        assert fetched.cycle_id == computed.cycle_id
        assert fetched.total_value == computed.total_value
        assert fetched.cash == computed.cash
        assert fetched.equity == computed.equity
        assert fetched.buying_power == computed.buying_power

        # 4. a row physically appears in portfolio_snapshots
        assert repo.count() == 1
        assert repo.latest() == saved
    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0001_baseline", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0001_baseline` failed:\n{down.stdout}\n{down.stderr}"
    )
