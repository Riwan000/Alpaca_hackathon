"""``strategy_hypotheses`` repository tests — task P4-DB-1.

Flow under test: one strategy-evaluation pass persists **all four** hypotheses
for a cycle — including the ones an agent rejected as NOT_VIABLE — and the
rejection reasoning is stored alongside.

- ``save_many`` writes four hypotheses in one transaction; ``list_for_cycle``
  reads them back in insertion order, rejected ones included;
- ``rejection_reason`` round-trips for the NOT_VIABLE ones;
- the P4-DB-1 confirm query — ``select strategy_type, verdict from
  strategy_hypotheses`` — shows all four;
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
from backend.db.strategy_repo import (
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'hypotheses_scratch.db'}"


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
    """A migrated scratch DB with a :class:`StrategyHypothesisRepository` bound to it."""
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        yield StrategyHypothesisRepository(engine)
    finally:
        engine.dispose()


def _four_hypotheses(cycle_id: str) -> list[StrategyHypothesisRecord]:
    """Two viable, two rejected — the shape a real evaluation pass produces."""
    return [
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="PROTECTIVE_PUT",
            verdict="ACCEPTED",
            legs=[{"symbol": "SPY260320P00500000", "side": "BUY", "ratio": 1}],
            metrics={"cost_pct_of_portfolio": 0.012, "downside_protection_pct": 0.9},
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="PUT_SPREAD",
            verdict="ACCEPTED",
            legs=[
                {"symbol": "SPY260320P00500000", "side": "BUY", "ratio": 1},
                {"symbol": "SPY260320P00460000", "side": "SELL", "ratio": 1},
            ],
            metrics={"cost_pct_of_portfolio": 0.006, "max_loss": 4000.0},
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="COLLAR",
            verdict="REJECTED",
            metrics={"cost_pct_of_portfolio": 0.0},
            rejection_reason="short call cap would clip the portfolio's core upside thesis",
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="NO_HEDGE",
            verdict="REJECTED",
            rejection_reason="current drawdown 12% already exceeds the 8% tolerance",
        ),
    ]


def test_four_hypotheses_persist_per_cycle_including_not_viable(
    repo: StrategyHypothesisRepository,
) -> None:
    """P4-DB-1: all four hypotheses land, rejected ones carry their reason."""
    cycle = "cycle_p4_db_1"
    saved = repo.save_many(_four_hypotheses(cycle))

    assert len(saved) == 4
    assert all(h.id is not None for h in saved)
    assert repo.count() == 4

    timeline = repo.list_for_cycle(cycle)
    assert [h.strategy_type for h in timeline] == [
        "PROTECTIVE_PUT",
        "PUT_SPREAD",
        "COLLAR",
        "NO_HEDGE",
    ]
    assert [h.verdict for h in timeline] == [
        "ACCEPTED",
        "ACCEPTED",
        "REJECTED",
        "REJECTED",
    ]

    rejected = [h for h in timeline if h.verdict == "REJECTED"]
    assert len(rejected) == 2
    assert all(h.rejection_reason for h in rejected)
    assert "tolerance" in next(
        h.rejection_reason for h in rejected if h.strategy_type == "NO_HEDGE"
    )


def test_confirm_query_shows_all_four(repo: StrategyHypothesisRepository) -> None:
    """The P4-DB-1 confirm: ``select strategy_type, verdict`` returns all four."""
    cycle = "cycle_confirm"
    repo.save_many(_four_hypotheses(cycle))

    with repo._engine.connect() as conn:
        rows = conn.execute(
            text(
                "select strategy_type, verdict from strategy_hypotheses "
                "where cycle_id = :cycle order by id"
            ),
            {"cycle": cycle},
        ).all()

    assert [tuple(r) for r in rows] == [
        ("PROTECTIVE_PUT", "ACCEPTED"),
        ("PUT_SPREAD", "ACCEPTED"),
        ("COLLAR", "REJECTED"),
        ("NO_HEDGE", "REJECTED"),
    ]


def test_create_round_trips_jsonb_columns(
    repo: StrategyHypothesisRepository,
) -> None:
    created = repo.create(
        StrategyHypothesisRecord(
            cycle_id="cycle_single",
            strategy_type="PROTECTIVE_PUT",
            verdict="ACCEPTED",
            legs=[{"symbol": "SPY260320P00500000", "ratio": 1}],
            metrics={"net_delta": -0.42, "breakevens": [478.5]},
        )
    )
    assert created.id is not None

    reloaded = repo.get(created.id)
    assert reloaded == created
    assert reloaded is not None
    assert reloaded.legs == [{"symbol": "SPY260320P00500000", "ratio": 1}]
    assert reloaded.metrics == {"net_delta": -0.42, "breakevens": [478.5]}


def test_list_for_cycle_does_not_bleed_across_cycles(
    repo: StrategyHypothesisRepository,
) -> None:
    repo.save_many(_four_hypotheses("cycle_a"))
    repo.save_many(_four_hypotheses("cycle_b"))

    assert len(repo.list_for_cycle("cycle_a")) == 4
    assert len(repo.list_for_cycle("cycle_b")) == 4
    assert len(repo.list_all()) == 8
    assert repo.list_for_cycle("nope") == []


def test_off_enum_verdict_is_refused(repo: StrategyHypothesisRepository) -> None:
    bad = StrategyHypothesisRecord(
        cycle_id="cycle_bad",
        strategy_type="PROTECTIVE_PUT",
        verdict="NOT_VIABLE",  # not a hypothesis_verdict_enum value
    )
    with pytest.raises(ValueError):
        repo.create(bad)

    # A bad verdict anywhere in a batch aborts the whole write.
    with pytest.raises(ValueError):
        repo.save_many([*_four_hypotheses("cycle_batch"), bad])
    assert repo.count() == 0
