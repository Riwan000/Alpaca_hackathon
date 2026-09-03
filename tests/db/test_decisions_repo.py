"""``strategy_decisions`` repository tests — task P4-DB-2.

Flow under test: the Strategy Manager records one decision per cycle — the
chosen hypothesis (or ``None`` for ``NO_TRADE``), the considered
``alternatives``, and the ``comparison`` table it reasoned over.

- a ``SELECT_STRATEGY`` decision links ``selected_hypothesis_id`` to a real
  ``strategy_hypotheses`` row; ``alternatives`` / ``comparison`` jsonb are
  non-empty;
- a ``NO_TRADE`` decision leaves ``selected_hypothesis_id`` null but still
  carries the alternatives it weighed;
- the P4-DB-2 confirm query — ``select action, rationale from
  strategy_decisions`` — shows a filled rationale;
- a dangling ``selected_hypothesis_id`` is rejected by the FK.
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
    StrategyDecisionRecord,
    StrategyDecisionRepository,
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'decisions_scratch.db'}"


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
def engine(tmp_path: Path):
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    eng = create_engine(normalize_driver(db_url))
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def decisions(engine) -> StrategyDecisionRepository:
    return StrategyDecisionRepository(engine)


@pytest.fixture
def hypotheses(engine) -> StrategyHypothesisRepository:
    return StrategyHypothesisRepository(engine)


_COMPARISON = [
    {"strategy": "PROTECTIVE_PUT", "cost": 1200.0, "downside_protection_pct": 0.9},
    {"strategy": "PUT_SPREAD", "cost": 600.0, "downside_protection_pct": 0.6},
]
_ALTERNATIVES = [
    {"strategy": "PUT_SPREAD", "viable": True, "cost": 600.0},
    {"strategy": "NO_HEDGE", "viable": False, "rejection_reason": "drawdown over tolerance"},
]


def test_select_strategy_decision_links_hypothesis_and_stores_jsonb(
    decisions: StrategyDecisionRepository,
    hypotheses: StrategyHypothesisRepository,
) -> None:
    """P4-DB-2: decision row links ``selected_hypothesis_id``; jsonb non-empty."""
    chosen = hypotheses.create(
        StrategyHypothesisRecord(
            cycle_id="cycle_p4_db_2",
            strategy_type="PROTECTIVE_PUT",
            verdict="ACCEPTED",
            legs=[{"symbol": "SPY260320P00500000", "ratio": 1}],
            metrics={"cost_pct_of_portfolio": 0.012},
        )
    )
    assert chosen.id is not None

    saved = decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_p4_db_2",
            action="SELECT_STRATEGY",
            rationale=(
                "Protective put buys the cleanest floor for the cost; the spread "
                "leaves a tail open below the short strike."
            ),
            selected_hypothesis_id=chosen.id,
            alternatives=_ALTERNATIVES,
            comparison=_COMPARISON,
        )
    )
    assert saved.id is not None

    reloaded = decisions.get(saved.id)
    assert reloaded == saved
    assert reloaded is not None
    assert reloaded.selected_hypothesis_id == chosen.id
    assert reloaded.alternatives == _ALTERNATIVES
    assert reloaded.comparison == _COMPARISON
    assert reloaded.alternatives  # non-empty
    assert reloaded.comparison  # non-empty


def test_confirm_query_shows_a_filled_rationale(
    decisions: StrategyDecisionRepository,
) -> None:
    """The P4-DB-2 confirm: ``select action, rationale`` returns real text."""
    decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_confirm",
            action="SELECT_STRATEGY",
            rationale="Chose the collar: it funds the put with the call and caps a rich name.",
            selected_hypothesis_id=None,
            alternatives=_ALTERNATIVES,
            comparison=_COMPARISON,
        )
    )

    with decisions._engine.connect() as conn:
        action, rationale = conn.execute(
            text(
                "select action, rationale from strategy_decisions "
                "where cycle_id = :cycle"
            ),
            {"cycle": "cycle_confirm"},
        ).one()

    assert action == "SELECT_STRATEGY"
    assert rationale and rationale.strip()


def test_no_trade_decision_keeps_null_selection_but_weighed_alternatives(
    decisions: StrategyDecisionRepository,
) -> None:
    saved = decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_no_trade",
            action="NO_TRADE",
            rationale="Every viable hedge costs more than the drawdown it removes.",
            selected_hypothesis_id=None,
            alternatives=_ALTERNATIVES,
            comparison=_COMPARISON,
        )
    )

    reloaded = decisions.get(saved.id)  # type: ignore[arg-type]
    assert reloaded is not None
    assert reloaded.action == "NO_TRADE"
    assert reloaded.selected_hypothesis_id is None
    assert reloaded.alternatives  # still recorded what it weighed
    assert reloaded.comparison


def test_for_cycle_and_latest(
    decisions: StrategyDecisionRepository,
) -> None:
    decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_a",
            action="NO_TRADE",
            rationale="a",
            alternatives=_ALTERNATIVES,
            comparison=_COMPARISON,
        )
    )
    second = decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_b",
            action="SELECT_STRATEGY",
            rationale="b",
            alternatives=_ALTERNATIVES,
            comparison=_COMPARISON,
        )
    )

    assert decisions.for_cycle("cycle_a").action == "NO_TRADE"  # type: ignore[union-attr]
    assert decisions.for_cycle("cycle_b").action == "SELECT_STRATEGY"  # type: ignore[union-attr]
    assert decisions.for_cycle("cycle_missing") is None
    assert decisions.latest() == second
    assert decisions.count() == 2


def test_dangling_hypothesis_fk_is_rejected(
    decisions: StrategyDecisionRepository,
) -> None:
    with pytest.raises(Exception):
        decisions.create(
            StrategyDecisionRecord(
                cycle_id="cycle_bad_fk",
                action="SELECT_STRATEGY",
                rationale="points at a hypothesis that was never written",
                selected_hypothesis_id=999_999,
                alternatives=_ALTERNATIVES,
                comparison=_COMPARISON,
            )
        )
    assert decisions.count() == 0
