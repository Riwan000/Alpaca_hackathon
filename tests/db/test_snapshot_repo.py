"""``portfolio_snapshots`` + ``positions`` repository tests — task P3-DB-2.

Flow under test: one analysis pass writes a snapshot plus its N positions in a
single transaction.

- save snapshot + N positions → both land, positions carry the snapshot's id,
  read-back equals what was saved;
- a bad position (missing ``symbol``) aborts the whole write — neither the
  snapshot nor the earlier positions remain.
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
from sqlalchemy.exc import IntegrityError

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'snapshot_repo_scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot(cycle_id: str) -> PortfolioSnapshotRecord:
    return PortfolioSnapshotRecord(
        cycle_id=cycle_id,
        total_value=decimal.Decimal("100000.0000"),
        cash=decimal.Decimal("25000.0000"),
        equity=decimal.Decimal("75000.0000"),
        buying_power=decimal.Decimal("50000.0000"),
        ts=datetime.datetime(2026, 9, 3, 15, 30, tzinfo=datetime.timezone.utc),
    )


def _positions(count: int) -> list[PositionRecord]:
    symbols = ["AAPL", "NVDA", "MSFT", "SPY", "QQQ"]
    return [
        PositionRecord(
            symbol=symbols[i],
            qty=decimal.Decimal("100.0000"),
            avg_price=decimal.Decimal("150.0000"),
            market_value=decimal.Decimal("15000.0000"),
            asset_class="us_equity",
            side="long",
        )
        for i in range(count)
    ]


@pytest.fixture
def repo(tmp_path: Path):
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        yield PortfolioSnapshotRepository(engine)
    finally:
        engine.dispose()


def test_save_snapshot_and_positions_one_transaction(
    repo: PortfolioSnapshotRepository,
) -> None:
    """P3-DB-2: snapshot + N positions persist together; read-back is unchanged."""
    saved = repo.save_with_positions(_snapshot("cycle_p3_db_2"), _positions(4))

    assert saved.snapshot.id is not None
    assert len(saved.positions) == 4
    assert all(p.id is not None for p in saved.positions)
    assert all(p.snapshot_id == saved.snapshot.id for p in saved.positions)

    assert repo.count() == 1
    assert repo.count_positions() == 4

    fetched = repo.positions_for(saved.snapshot.id)
    assert fetched == list(saved.positions)
    assert [p.symbol for p in fetched] == ["AAPL", "NVDA", "MSFT", "SPY"]

    round_tripped = repo.get(saved.snapshot.id)
    assert round_tripped == saved.snapshot


def test_partial_failure_rolls_back_snapshot_and_positions(
    repo: PortfolioSnapshotRepository,
) -> None:
    """A bad position aborts the whole pass — no snapshot, no positions."""
    good = _positions(2)
    bad = PositionRecord(
        symbol=None,  # type: ignore[arg-type]  # violates positions.symbol NOT NULL
        qty=decimal.Decimal("1.0000"),
        avg_price=decimal.Decimal("1.0000"),
        market_value=decimal.Decimal("1.0000"),
        asset_class="us_equity",
        side="long",
    )

    with pytest.raises((IntegrityError, Exception)):
        repo.save_with_positions(_snapshot("cycle_rollback"), [*good, bad])

    assert repo.count() == 0
    assert repo.count_positions() == 0


def test_empty_positions_still_writes_the_snapshot(
    repo: PortfolioSnapshotRepository,
) -> None:
    """An all-cash portfolio (no positions) is a valid pass."""
    saved = repo.save_with_positions(_snapshot("cycle_all_cash"), [])
    assert saved.snapshot.id is not None
    assert saved.positions == ()
    assert repo.count() == 1
    assert repo.count_positions() == 0


def test_second_pass_adds_a_distinct_snapshot(
    repo: PortfolioSnapshotRepository,
) -> None:
    """Confirm shape: after another /analyze, one more snapshot with its own positions."""
    first = repo.save_with_positions(_snapshot("cycle_a"), _positions(3))
    second = repo.save_with_positions(_snapshot("cycle_b"), _positions(2))

    assert first.snapshot.id != second.snapshot.id
    assert repo.count() == 2
    assert repo.count_positions() == 5
    assert len(repo.positions_for(first.snapshot.id)) == 3
    assert len(repo.positions_for(second.snapshot.id)) == 2
