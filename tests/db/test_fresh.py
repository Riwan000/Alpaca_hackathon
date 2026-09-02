"""Fresh database migrate and seed lifecycle tests — task P1-DB-16.

Verifies that drop/downgrade, migrate up, and seed run cleanly from scratch
with exit code 0 and produce a fully initialized and consistent database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import MetaData, Table, create_engine, inspect, select

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.seed import DEMO_POSITIONS, DEMO_SNAPSHOT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'fresh_scratch.db'}"


def _run_cmd(cmd: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def test_db_fresh_migrate_then_seed(tmp_path: Path) -> None:
    """Task P1-DB-16: CI job db-fresh — drop/downgrade, migrate, seed, all exit 0."""
    db_url = _scratch_url(tmp_path)

    # 1. Step 1: Migrate to head on fresh database
    migrate_res = _run_cmd(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        db_url=db_url,
    )
    assert migrate_res.returncode == 0, (
        f"Migration failed on fresh DB:\n{migrate_res.stdout}\n{migrate_res.stderr}"
    )

    # 2. Step 2: Seed the demo portfolio
    seed_res = _run_cmd(
        [sys.executable, "-m", "backend.seed", "--url", db_url],
        db_url=db_url,
    )
    assert seed_res.returncode == 0, (
        f"Seeding failed on fresh DB:\n{seed_res.stdout}\n{seed_res.stderr}"
    )
    assert "[SEED] Successfully seeded" in seed_res.stdout

    # 3. Step 3: Verify contents in DB
    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        expected_tables = [
            "portfolio_snapshots",
            "positions",
            "agent_runs",
            "strategy_hypotheses",
            "strategy_decisions",
            "risk_checks",
            "orders",
            "fills",
            "monitoring_events",
            "performance",
        ]
        for tbl in expected_tables:
            assert tbl in table_names, f"Table '{tbl}' missing after fresh migrate+seed"

        metadata = MetaData()
        portfolio_snapshots_table = Table("portfolio_snapshots", metadata, autoload_with=engine)
        positions_table = Table("positions", metadata, autoload_with=engine)

        with engine.connect() as conn:
            snaps = conn.execute(select(portfolio_snapshots_table)).mappings().all()
            assert len(snaps) == 1
            assert snaps[0]["cycle_id"] == DEMO_SNAPSHOT["cycle_id"]

            positions = conn.execute(select(positions_table)).mappings().all()
            assert len(positions) == len(DEMO_POSITIONS)
    finally:
        engine.dispose()

    # 4. Step 4: Drop/downgrade to base and verify clean reset
    down_res = _run_cmd(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "downgrade", "base"],
        db_url=db_url,
    )
    assert down_res.returncode == 0, (
        f"Downgrade to base failed:\n{down_res.stdout}\n{down_res.stderr}"
    )

    # 5. Step 5: Re-migrate and re-seed to confirm reproducibility
    re_migrate = _run_cmd(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        db_url=db_url,
    )
    assert re_migrate.returncode == 0

    re_seed = _run_cmd(
        [sys.executable, "-m", "backend.seed", "--url", db_url],
        db_url=db_url,
    )
    assert re_seed.returncode == 0
    assert "[SEED] Successfully seeded" in re_seed.stdout
