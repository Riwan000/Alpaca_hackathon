"""``agent_runs`` repository tests — task P3-DB-1.

Flow under test: ``create`` a started run, then ``finish`` it.

- create → finish(outputs) updates ``outputs`` + ``duration_ms`` (and stamps
  ``finished_at``), leaves ``error`` null;
- finish(error) stores the message and leaves ``outputs`` null;
- ``list_for_cycle`` returns a row per agent in start order — the timeline read.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.agent_runs_repo import AgentRunRecord, AgentRunRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'agent_runs_scratch.db'}"


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
def repo(tmp_path: Path):
    """A migrated scratch DB with an :class:`AgentRunRepository` bound to it."""
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        yield AgentRunRepository(engine)
    finally:
        engine.dispose()


def test_create_then_finish_with_outputs(repo: AgentRunRepository) -> None:
    """create → finish(outputs): outputs + duration persisted, error stays null."""
    created = repo.create(
        AgentRunRecord(
            cycle_id="cycle_p3_db_1",
            agent_name="market_agent",
            inputs={"symbols": ["SPY", "AAPL"], "lookback_days": 30},
        )
    )
    assert created.id is not None
    assert created.outputs is None
    assert created.error is None
    assert created.duration_ms is None
    assert created.finished_at is None

    finished = repo.finish(
        created.id,
        outputs={"beta": 1.03, "vol": 0.18},
        duration_ms=1420,
    )
    assert finished.outputs == {"beta": 1.03, "vol": 0.18}
    assert finished.duration_ms == 1420
    assert finished.error is None
    assert finished.finished_at is not None
    assert finished.inputs == {"symbols": ["SPY", "AAPL"], "lookback_days": 30}

    # Re-read straight from the DB — the update actually landed.
    reloaded = repo.get(created.id)
    assert reloaded == finished
    assert reloaded is not None
    assert reloaded.outputs == {"beta": 1.03, "vol": 0.18}
    assert reloaded.duration_ms == 1420
    assert reloaded.error is None


def test_finish_with_error_leaves_outputs_null(repo: AgentRunRepository) -> None:
    """finish(error): message stored, outputs left null, duration still recorded."""
    created = repo.create(
        AgentRunRecord(cycle_id="cycle_p3_db_1", agent_name="news_agent")
    )
    assert created.id is not None

    finished = repo.finish(
        created.id,
        error="upstream feed returned 503",
        duration_ms=310,
    )
    assert finished.error == "upstream feed returned 503"
    assert finished.outputs is None
    assert finished.duration_ms == 310
    assert finished.finished_at is not None

    reloaded = repo.get(created.id)
    assert reloaded is not None
    assert reloaded.error == "upstream feed returned 503"
    assert reloaded.outputs is None


def test_finish_rejects_both_or_neither(repo: AgentRunRepository) -> None:
    """finish() takes exactly one of outputs / error."""
    created = repo.create(
        AgentRunRecord(cycle_id="cycle_p3_db_1", agent_name="risk_agent")
    )
    assert created.id is not None

    with pytest.raises(ValueError):
        repo.finish(created.id, outputs={"ok": True}, error="boom", duration_ms=10)
    with pytest.raises(ValueError):
        repo.finish(created.id, duration_ms=10)
    with pytest.raises(ValueError):
        repo.finish(created.id, outputs={"ok": True}, duration_ms=-1)


def test_finish_unknown_id_raises(repo: AgentRunRepository) -> None:
    with pytest.raises(LookupError):
        repo.finish(999_999, outputs={"ok": True}, duration_ms=5)


def test_list_for_cycle_is_a_row_per_agent_in_start_order(
    repo: AgentRunRepository,
) -> None:
    """The P3-DB-1 confirm: one analysis → a row per agent, ordered by start."""
    cycle = "cycle_timeline"
    names = ["market_agent", "news_agent", "options_agent", "risk_agent"]
    for i, name in enumerate(names):
        run = repo.create(AgentRunRecord(cycle_id=cycle, agent_name=name))
        assert run.id is not None
        repo.finish(run.id, outputs={"step": i}, duration_ms=100 + i)

    # A run from an unrelated cycle must not bleed in.
    other = repo.create(AgentRunRecord(cycle_id="other_cycle", agent_name="market_agent"))
    assert other.id is not None
    repo.finish(other.id, outputs={}, duration_ms=1)

    timeline = repo.list_for_cycle(cycle)
    assert [r.agent_name for r in timeline] == names
    assert [r.duration_ms for r in timeline] == [100, 101, 102, 103]
    assert repo.count() == len(names) + 1
