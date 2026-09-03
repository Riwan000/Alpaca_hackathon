"""``risk_checks`` repository tests — task P5-DB-1.

Flow under test: the Phase 5 risk gate writes exactly **one** ``risk_checks``
row per risk evaluation — the verdict, the deterministic checklist, and the
reasons behind the verdict.

- one row per evaluation; ``list_for_cycle`` reads it back;
- ``violations`` is non-empty on a ``REJECT`` (and the repo refuses a ``REJECT``
  with no violation);
- ``modifications`` is non-empty on a ``MODIFY`` (and the repo refuses a
  ``MODIFY`` with no modification);
- the P5-DB-1 confirm query — ``select verdict, violations from risk_checks`` —
  reflects the decision;
- an off-enum ``verdict`` is refused before it reaches the database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'risk_checks_scratch.db'}"


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
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        yield RiskCheckRepository(engine)
    finally:
        engine.dispose()


def _approve(cycle_id: str) -> RiskCheckRecord:
    return RiskCheckRecord(
        cycle_id=cycle_id,
        verdict="APPROVE",
        checks=[
            {"name": "hedge_budget", "category": "COST", "passed": True, "observed": 0.011, "limit": 0.02},
            {"name": "max_hedge_ratio", "category": "POSITION_LIMITS", "passed": True, "observed": 0.6, "limit": 1.0},
        ],
        warnings=["front-month IV is elevated"],
    )


def _reject(cycle_id: str) -> RiskCheckRecord:
    return RiskCheckRecord(
        cycle_id=cycle_id,
        verdict="REJECT",
        checks=[{"name": "hedge_budget", "category": "COST", "passed": False, "observed": 0.031, "limit": 0.02}],
        violations=["hedge cost 3.1% of portfolio exceeds the 2.0% budget"],
    )


def _modify(cycle_id: str) -> RiskCheckRecord:
    return RiskCheckRecord(
        cycle_id=cycle_id,
        verdict="MODIFY",
        checks=[{"name": "contracts", "category": "POSITION_LIMITS", "passed": False, "observed": 12, "limit": 8}],
        modifications=[
            {"field": "contracts", "from_value": 12, "to_value": 8, "reason": "trim to the position limit"}
        ],
    )


def test_one_row_per_evaluation_round_trips(repo: RiskCheckRepository) -> None:
    """P5-DB-1: an APPROVE evaluation is one row and reads back unchanged."""
    cycle = "cycle_p5_db_1"
    saved = repo.create(_approve(cycle))

    assert saved.id is not None
    assert repo.count() == 1

    reloaded = repo.for_cycle(cycle)
    assert reloaded == saved
    assert reloaded is not None
    assert reloaded.verdict == "APPROVE"
    assert reloaded.checks[0]["name"] == "hedge_budget"
    assert reloaded.warnings == ["front-month IV is elevated"]
    assert reloaded.violations is None


def test_reject_carries_violations(repo: RiskCheckRepository) -> None:
    saved = repo.create(_reject("cycle_reject"))
    assert saved.verdict == "REJECT"
    assert saved.violations
    assert "budget" in saved.violations[0]


def test_modify_carries_modifications(repo: RiskCheckRepository) -> None:
    saved = repo.create(_modify("cycle_modify"))
    assert saved.verdict == "MODIFY"
    assert saved.modifications
    assert saved.modifications[0]["to_value"] == 8


def test_confirm_query_reflects_the_decision(repo: RiskCheckRepository) -> None:
    """The P5-DB-1 confirm: ``select verdict, violations from risk_checks``."""
    repo.create(_approve("cycle_a"))
    repo.create(_reject("cycle_b"))

    with repo._engine.connect() as conn:
        rows = conn.execute(
            text("select cycle_id, verdict, violations from risk_checks order by id")
        ).all()

    by_cycle = {r[0]: (r[1], r[2]) for r in rows}
    assert by_cycle["cycle_a"][0] == "APPROVE"
    assert by_cycle["cycle_b"][0] == "REJECT"
    # violations column is populated (JSON text on SQLite) for the REJECT.
    assert by_cycle["cycle_b"][1] and "budget" in by_cycle["cycle_b"][1]


def test_reject_without_a_violation_is_refused(repo: RiskCheckRepository) -> None:
    with pytest.raises(ValueError):
        repo.create(RiskCheckRecord(cycle_id="c", verdict="REJECT", violations=[]))
    assert repo.count() == 0


def test_modify_without_a_modification_is_refused(repo: RiskCheckRepository) -> None:
    with pytest.raises(ValueError):
        repo.create(RiskCheckRecord(cycle_id="c", verdict="MODIFY", modifications=None))
    assert repo.count() == 0


def test_approve_with_a_violation_is_refused(repo: RiskCheckRepository) -> None:
    with pytest.raises(ValueError):
        repo.create(
            RiskCheckRecord(cycle_id="c", verdict="APPROVE", violations=["nope"])
        )
    assert repo.count() == 0


def test_off_enum_verdict_is_refused(repo: RiskCheckRepository) -> None:
    with pytest.raises(ValueError):
        repo.create(RiskCheckRecord(cycle_id="c", verdict="APPROVED"))
    assert repo.count() == 0


def test_list_for_cycle_does_not_bleed_across_cycles(repo: RiskCheckRepository) -> None:
    repo.create(_approve("cycle_a"))
    repo.create(_reject("cycle_b"))
    repo.create(_modify("cycle_b"))

    assert len(repo.list_for_cycle("cycle_a")) == 1
    assert len(repo.list_for_cycle("cycle_b")) == 2
    assert len(repo.list_all()) == 3
    assert repo.list_for_cycle("nope") == []
    # for_cycle returns the latest row for a re-evaluated cycle.
    assert repo.for_cycle("cycle_b").verdict == "MODIFY"
