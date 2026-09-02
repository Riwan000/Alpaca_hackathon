"""Demo portfolio seeding tests — task P1-DB-15.

Tests that seed.py loads a known demo portfolio (one snapshot + its positions)
with exact value equality against the canonical fixture.
"""

from __future__ import annotations

import decimal
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import MetaData, Table, create_engine, select

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.seed import DEMO_POSITIONS, DEMO_SNAPSHOT, seed_demo_portfolio

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'seed_scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def test_seed_demo_state(tmp_path: Path) -> None:
    """Task P1-DB-15: after seed: exactly one snapshot, its positions, values equal the fixture."""
    db_url = _scratch_url(tmp_path)

    # 1. Apply migrations to head
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    # 2. Run seed
    snap_id, pos_count = seed_demo_portfolio(db_url=db_url, clear_existing=True)
    assert snap_id is not None
    assert pos_count == len(DEMO_POSITIONS)

    # 3. Verify snapshot and positions in database
    engine = create_engine(normalize_driver(db_url))
    try:
        metadata = MetaData()
        portfolio_snapshots_table = Table("portfolio_snapshots", metadata, autoload_with=engine)
        positions_table = Table("positions", metadata, autoload_with=engine)

        with engine.connect() as conn:
            # Verify exactly one snapshot
            snapshots = conn.execute(select(portfolio_snapshots_table)).mappings().all()
            assert len(snapshots) == 1, f"Expected 1 snapshot, got {len(snapshots)}"
            snap = snapshots[0]
            assert snap["cycle_id"] == DEMO_SNAPSHOT["cycle_id"]
            assert snap["total_value"] == DEMO_SNAPSHOT["total_value"]
            assert snap["cash"] == DEMO_SNAPSHOT["cash"]
            assert snap["equity"] == DEMO_SNAPSHOT["equity"]
            assert snap["buying_power"] == DEMO_SNAPSHOT["buying_power"]

            # Verify positions
            positions = conn.execute(
                select(positions_table).where(positions_table.c.snapshot_id == snap["id"])
            ).mappings().all()
            assert len(positions) == len(DEMO_POSITIONS)

            pos_by_symbol = {p["symbol"]: p for p in positions}
            for fixture_pos in DEMO_POSITIONS:
                sym = fixture_pos["symbol"]
                assert sym in pos_by_symbol, f"Position symbol {sym} missing"
                db_pos = pos_by_symbol[sym]
                assert db_pos["qty"] == fixture_pos["qty"]
                assert db_pos["avg_price"] == fixture_pos["avg_price"]
                assert db_pos["market_value"] == fixture_pos["market_value"]
                assert db_pos["asset_class"] == fixture_pos["asset_class"]
                assert db_pos["side"] == fixture_pos["side"]

            # Verify sum of market values equals equity
            total_mv = sum(p["market_value"] for p in positions)
            assert total_mv == DEMO_SNAPSHOT["equity"]

            # 4. Test idempotency: re-running seed clears and reseeds cleanly
            seed_demo_portfolio(db_url=db_url, clear_existing=True)
            snapshots_after = conn.execute(select(portfolio_snapshots_table)).mappings().all()
            assert len(snapshots_after) == 1
            positions_after = conn.execute(select(positions_table)).mappings().all()
            assert len(positions_after) == len(DEMO_POSITIONS)

    finally:
        engine.dispose()


def test_seed_cli_entrypoint(tmp_path: Path) -> None:
    """Test running seed via `python -m backend.seed --url ...` CLI entrypoint."""
    db_url = _scratch_url(tmp_path)
    _run_alembic("upgrade", "head", db_url=db_url)

    res = subprocess.run(
        [sys.executable, "-m", "backend.seed", "--url", db_url],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Seed CLI failed:\n{res.stdout}\n{res.stderr}"
    assert "[SEED] Successfully seeded" in res.stdout
