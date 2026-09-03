"""Tests for demo dataset backup and restore — task P8-DB-4."""

from __future__ import annotations

import decimal
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.backup import export_demo_dataset, restore_demo_dataset
from backend.db.performance_repo import PerformanceRecord, PerformanceRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


def _create_scratch_db(tmp_path: Path, name: str):
    db_url = f"sqlite:///{tmp_path / name}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed: {proc.stdout} {proc.stderr}"
    return create_engine(normalize_driver(db_url))


def test_backup_and_restore_roundtrip(tmp_path: Path) -> None:
    source_engine = _create_scratch_db(tmp_path, "source.db")
    target_engine = _create_scratch_db(tmp_path, "target.db")

    # Seed source DB with a performance row
    repo = PerformanceRepository(source_engine)
    repo.save(
        PerformanceRecord(
            cycle_id="cycle_backup_1",
            portfolio_pnl=decimal.Decimal("-1000.0000"),
            hedge_pnl=decimal.Decimal("800.0000"),
            net_pnl=decimal.Decimal("-200.0000"),
            drawdown=decimal.Decimal("-0.0020"),
            hedge_cost=decimal.Decimal("100.0000"),
            benchmark_pnl=decimal.Decimal("-1000.0000"),
        )
    )

    backup_file = tmp_path / "demo_backup.json"
    exported_counts = export_demo_dataset(source_engine, backup_file)
    assert backup_file.exists()
    assert exported_counts["performance"] == 1

    restored_counts = restore_demo_dataset(target_engine, backup_file)
    assert restored_counts["performance"] == 1

    target_repo = PerformanceRepository(target_engine)
    latest = target_repo.get_latest()
    assert latest is not None
    assert latest.cycle_id == "cycle_backup_1"
    assert latest.net_pnl == decimal.Decimal("-200.0000")
