"""Stub-router tests — task P1-BE-15.

Every stub route answers ``200`` and its body validates against the contract it
claims to return.

``/execution`` moved off the stub list once it became a real DB-backed
read-back (see ``backend/api/exec_readback.py``): it now returns 404 on an
empty database instead of an unconditional fixture, so it can't be exercised
with a bare, unseeded client the way a stub can. Its correctness is covered by
``tests/api/test_exec_readback.py`` instead; it stays in ``CONTRACT_ROUTES``
so the "every contract has an endpoint" coverage check still counts it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.models import (
    ExecutionPlan,
    ExecutionResult,
    HedgeContext,
    MonitoringState,
    RiskDecision,
    StrategyDecision,
    StrategyHypothesis,
)

# route path -> the contract model its body must satisfy, for routes still
# backed by a canonical fixture.
STUB_ROUTES: dict[str, type] = {
    "/context": HedgeContext,
    "/strategy/hypothesis": StrategyHypothesis,
    "/strategy": StrategyDecision,
    "/risk": RiskDecision,
    "/execution/plan": ExecutionPlan,
    "/monitoring": MonitoringState,
}

# every top-level contract must be exposed at *some* GET endpoint, stub or real
CONTRACT_ROUTES: dict[str, type] = {**STUB_ROUTES, "/execution": ExecutionResult}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(("path", "model"), list(STUB_ROUTES.items()), ids=list(STUB_ROUTES))
def test_stub_route_returns_valid_contract(path: str, model: type, client: TestClient) -> None:
    response = client.get(path)

    assert response.status_code == 200, response.text
    parsed = model.model_validate(response.json())
    # the round-trip is lossless — re-dumping matches the wire body
    assert model.model_validate(parsed.model_dump(mode="json")) == parsed


def test_every_top_level_contract_has_a_route() -> None:
    """The route table covers every contract in ``backend.models.CONTRACT_MODELS``."""
    from backend.models import CONTRACT_MODELS

    assert set(CONTRACT_ROUTES.values()) == set(CONTRACT_MODELS)
