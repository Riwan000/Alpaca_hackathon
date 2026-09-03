"""Strategy read-back endpoint tests — task P4-DB-3.

* ``GET /strategy/hypotheses?cycle_id=`` filters by ``cycle_id`` and **includes
  rejected / NOT_VIABLE hypotheses**; without ``cycle_id`` it returns every one.
* ``GET /strategy/decision?cycle_id=`` returns that cycle's decision (rationale,
  alternatives, comparison); without ``cycle_id`` the most recent one; ``404``
  when nothing has been recorded.
* Counts returned match the database (the P4-DB-3 confirm).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
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


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _hypotheses(cycle_id: str) -> list[StrategyHypothesisRecord]:
    return [
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="PROTECTIVE_PUT",
            verdict="ACCEPTED",
            legs=[{"symbol": "SPY260320P00500000", "ratio": 1}],
            metrics={"cost_pct_of_portfolio": 0.012},
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="PUT_SPREAD",
            verdict="ACCEPTED",
            metrics={"cost_pct_of_portfolio": 0.006},
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="COLLAR",
            verdict="REJECTED",
            rejection_reason="short call clips the portfolio's core upside thesis",
        ),
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type="NO_HEDGE",
            verdict="REJECTED",
            rejection_reason="drawdown already exceeds tolerance",
        ),
    ]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App wired to a migrated scratch DB seeded with two cycles of strategy output."""
    db_url = f"sqlite:///{tmp_path / 'strategy_readback_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)

    hypo_repo = StrategyHypothesisRepository(engine)
    dec_repo = StrategyDecisionRepository(engine)

    # cycle_a: full four hypotheses + a SELECT_STRATEGY decision on the put.
    saved_a = hypo_repo.save_many(_hypotheses("cycle_a"))
    dec_repo.create(
        StrategyDecisionRecord(
            cycle_id="cycle_a",
            action="SELECT_STRATEGY",
            rationale="Protective put buys the cleanest floor for the cost.",
            selected_hypothesis_id=saved_a[0].id,
            alternatives=[{"strategy": "PUT_SPREAD", "viable": True}],
            comparison=[{"strategy": "PROTECTIVE_PUT", "cost": 1200.0}],
        )
    )

    # cycle_b: four hypotheses + a NO_TRADE decision.
    hypo_repo.save_many(_hypotheses("cycle_b"))
    dec_repo.create(
        StrategyDecisionRecord(
            cycle_id="cycle_b",
            action="NO_TRADE",
            rationale="Every viable hedge costs more than the drawdown it removes.",
            selected_hypothesis_id=None,
            alternatives=[{"strategy": "COLLAR", "viable": False}],
            comparison=[{"strategy": "NO_HEDGE", "cost": 0.0}],
        )
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_hypotheses_filtered_by_cycle_include_rejected(client: TestClient) -> None:
    response = client.get("/strategy/hypotheses", params={"cycle_id": "cycle_a"})

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [r["strategy_type"] for r in rows] == [
        "PROTECTIVE_PUT",
        "PUT_SPREAD",
        "COLLAR",
        "NO_HEDGE",
    ]
    assert all(r["cycle_id"] == "cycle_a" for r in rows)

    rejected = [r for r in rows if r["verdict"] == "REJECTED"]
    assert len(rejected) == 2
    assert all(r["rejection_reason"] for r in rejected)


def test_hypotheses_without_cycle_returns_all(client: TestClient) -> None:
    rows = client.get("/strategy/hypotheses").json()

    assert len(rows) == 8
    assert {r["cycle_id"] for r in rows} == {"cycle_a", "cycle_b"}


def test_decision_filtered_by_cycle(client: TestClient) -> None:
    body = client.get("/strategy/decision", params={"cycle_id": "cycle_a"}).json()

    assert body["cycle_id"] == "cycle_a"
    assert body["action"] == "SELECT_STRATEGY"
    assert body["rationale"].strip()
    assert body["selected_hypothesis_id"] is not None
    assert body["alternatives"]
    assert body["comparison"]


def test_decision_no_trade_cycle_has_null_selection(client: TestClient) -> None:
    body = client.get("/strategy/decision", params={"cycle_id": "cycle_b"}).json()

    assert body["action"] == "NO_TRADE"
    assert body["selected_hypothesis_id"] is None
    assert body["alternatives"]  # still records what was weighed


def test_decision_without_cycle_returns_latest(client: TestClient) -> None:
    body = client.get("/strategy/decision").json()

    # cycle_b's decision was written last.
    assert body["cycle_id"] == "cycle_b"


def test_decision_404_when_cycle_has_none(client: TestClient) -> None:
    response = client.get("/strategy/decision", params={"cycle_id": "cycle_missing"})

    assert response.status_code == 404


def test_returned_counts_match_the_db(client: TestClient) -> None:
    """The P4-DB-3 confirm: endpoint counts reconcile with the tables."""
    all_hypotheses = client.get("/strategy/hypotheses").json()
    cycle_a = client.get("/strategy/hypotheses", params={"cycle_id": "cycle_a"}).json()

    engine = client.app.dependency_overrides[get_readback_engine]()
    hypo_repo = StrategyHypothesisRepository(engine)
    dec_repo = StrategyDecisionRepository(engine)

    assert len(all_hypotheses) == hypo_repo.count() == 8
    assert len(cycle_a) == len(hypo_repo.list_for_cycle("cycle_a")) == 4
    assert dec_repo.count() == 2


def test_decision_404_when_no_decision_recorded(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'empty_strategy_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            assert test_client.get("/strategy/decision").status_code == 404
            assert test_client.get("/strategy/hypotheses").json() == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
