"""``POST /strategy/evaluate`` integration tests — task P4-BE-11 / issue #113.

Confirms:
- 200 response with a schema-valid :class:`~backend.models.strategy.StrategyDecision`.
- Body validates against the model (``decision``, ``cycle_id``, ``rationale``).
- Exactly 4 hypotheses (one per strategy family) are persisted in the DB.
- Exactly 1 decision is persisted in the DB.
- The selected hypothesis (when SELECT_STRATEGY) has a matching DB row.
- NO_TRADE / REASSESS paths leave ``selected_hypothesis_id`` NULL in the DB.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.api.strategy_evaluate import get_strategy_llm_client
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.strategy_repo import (
    StrategyDecisionRepository,
    StrategyHypothesisRepository,
)
from backend.models.enums import DecisionType
from backend.models.strategy import StrategyDecision

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_GOLDEN = (
    _REPO_ROOT / "tests" / "fixtures" / "analyze" / "hedge_context_golden.json"
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _fake_llm_select(strategy_type: str, *, confidence: float = 0.9) -> Any:
    """Build a FakeLLMClient whose response selects ``strategy_type``."""
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": strategy_type,
            "rationale": f"Selected {strategy_type} as the best hedge for this cycle.",
            "confidence": confidence,
        }
    )
    return fake


def _fake_llm_no_trade() -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {
            "decision": "NO_TRADE",
            "selected_strategy": None,
            "rationale": "Every viable hedge costs more than the drawdown benefit.",
            "confidence": 0.85,
        }
    )
    return fake


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _migrated_engine(tmp_path: Path):
    """A migrated scratch SQLite engine, disposed on teardown."""
    db_url = f"sqlite:///{tmp_path / 'strategy_eval_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, (
        f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"
    )
    engine = create_engine(normalize_driver(db_url), future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def _golden_context() -> dict[str, Any]:
    """The golden HedgeContext fixture as a raw dict."""
    return json.loads(_GOLDEN.read_text("utf-8"))


@pytest.fixture
def client_select(_migrated_engine, _golden_context) -> Iterator[TestClient]:
    """App wired to the scratch DB + a FakeLLM that selects PROTECTIVE_PUT."""
    fake = _fake_llm_select("PROTECTIVE_PUT")
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: _migrated_engine
    app.dependency_overrides[get_strategy_llm_client] = lambda: fake
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client_no_trade(_migrated_engine, _golden_context) -> Iterator[TestClient]:
    """App wired to the scratch DB + a FakeLLM that returns NO_TRADE."""
    fake = _fake_llm_no_trade()
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: _migrated_engine
    app.dependency_overrides[get_strategy_llm_client] = lambda: fake
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# tests — issue #113 confirms
# ---------------------------------------------------------------------------


def test_200_response_and_body_validates(
    client_select: TestClient, _golden_context: dict[str, Any]
) -> None:
    """200; body must be a schema-valid StrategyDecision."""
    response = client_select.post("/strategy/evaluate", json=_golden_context)

    assert response.status_code == 200, response.text
    body = response.json()

    # Validate the shape against the Pydantic model
    decision = StrategyDecision.model_validate(body)
    assert decision.cycle_id == _golden_context["cycle_id"]
    assert decision.decision in DecisionType
    assert decision.rationale.strip()


def test_persists_four_hypotheses(
    client_select: TestClient,
    _migrated_engine,
    _golden_context: dict[str, Any],
) -> None:
    """Exactly 4 hypotheses (one per strategy family) must be written to the DB."""
    response = client_select.post("/strategy/evaluate", json=_golden_context)
    assert response.status_code == 200, response.text

    cycle_id = _golden_context["cycle_id"]
    hypo_repo = StrategyHypothesisRepository(_migrated_engine)
    rows = hypo_repo.list_for_cycle(cycle_id)

    assert len(rows) == 4, f"expected 4 hypotheses, got {len(rows)}"
    strategy_types = {r.strategy_type for r in rows}
    assert strategy_types == {"PROTECTIVE_PUT", "PUT_SPREAD", "COLLAR", "NO_HEDGE"}


def test_persists_one_decision(
    client_select: TestClient,
    _migrated_engine,
    _golden_context: dict[str, Any],
) -> None:
    """Exactly 1 decision must be written to the DB."""
    response = client_select.post("/strategy/evaluate", json=_golden_context)
    assert response.status_code == 200, response.text

    dec_repo = StrategyDecisionRepository(_migrated_engine)
    assert dec_repo.count() == 1


def test_select_strategy_decision_has_selected_hypothesis_id(
    client_select: TestClient,
    _migrated_engine,
    _golden_context: dict[str, Any],
) -> None:
    """When the decision is SELECT_STRATEGY, ``selected_hypothesis_id`` must be set."""
    response = client_select.post("/strategy/evaluate", json=_golden_context)
    assert response.status_code == 200, response.text

    body = response.json()
    if body["decision"] == "SELECT_STRATEGY":
        dec_repo = StrategyDecisionRepository(_migrated_engine)
        record = dec_repo.latest()
        assert record is not None
        assert record.selected_hypothesis_id is not None


def test_no_trade_decision_has_null_selected_hypothesis_id(
    client_no_trade: TestClient,
    _migrated_engine,
    _golden_context: dict[str, Any],
) -> None:
    """When the decision is NO_TRADE/REASSESS, ``selected_hypothesis_id`` must be NULL."""
    response = client_no_trade.post("/strategy/evaluate", json=_golden_context)
    assert response.status_code == 200, response.text

    body = response.json()
    dec_repo = StrategyDecisionRepository(_migrated_engine)
    record = dec_repo.latest()
    assert record is not None
    if body["decision"] in ("NO_TRADE", "REASSESS"):
        assert record.selected_hypothesis_id is None


def test_response_body_includes_hypotheses_as_alternatives(
    client_select: TestClient,
    _golden_context: dict[str, Any],
) -> None:
    """The returned StrategyDecision body should include the alternatives list."""
    response = client_select.post("/strategy/evaluate", json=_golden_context)
    assert response.status_code == 200, response.text
    body = response.json()

    # The decision always carries alternatives (even if empty on NO_TRADE with no
    # viable set). For the golden context at least one viable hypothesis exists.
    assert isinstance(body.get("alternatives"), list)


def test_repeated_calls_each_persist_four_hypotheses(
    client_select: TestClient,
    _migrated_engine,
    _golden_context: dict[str, Any],
) -> None:
    """Each call is independent — two calls → 8 hypothesis rows, 2 decision rows."""
    r1 = client_select.post("/strategy/evaluate", json=_golden_context)
    r2 = client_select.post("/strategy/evaluate", json=_golden_context)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    hypo_repo = StrategyHypothesisRepository(_migrated_engine)
    dec_repo = StrategyDecisionRepository(_migrated_engine)

    assert hypo_repo.count() == 8
    assert dec_repo.count() == 2


def test_low_confidence_llm_persists_reassess_decision(
    _migrated_engine, _golden_context: dict[str, Any]
) -> None:
    """Low-confidence LLM response → REASSESS decision persisted correctly."""
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PROTECTIVE_PUT",
            "rationale": "Uncertain pick.",
            "confidence": 0.2,  # below 0.5 threshold → REASSESS
        }
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: _migrated_engine
    app.dependency_overrides[get_strategy_llm_client] = lambda: fake
    try:
        with TestClient(app) as tc:
            response = tc.post("/strategy/evaluate", json=_golden_context)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "REASSESS"

    dec_repo = StrategyDecisionRepository(_migrated_engine)
    record = dec_repo.latest()
    assert record is not None
    assert record.action == "REASSESS"
    assert record.selected_hypothesis_id is None
