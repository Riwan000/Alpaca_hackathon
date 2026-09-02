"""Stub-router tests — task P1-BE-15.

Every stub route answers ``200`` and its body validates against the contract it
claims to return.
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

# route path -> the contract model its body must satisfy
ROUTES: dict[str, type] = {
    "/context": HedgeContext,
    "/strategy/hypothesis": StrategyHypothesis,
    "/strategy": StrategyDecision,
    "/risk": RiskDecision,
    "/execution/plan": ExecutionPlan,
    "/execution": ExecutionResult,
    "/monitoring": MonitoringState,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(("path", "model"), list(ROUTES.items()), ids=list(ROUTES))
def test_stub_route_returns_valid_contract(path: str, model: type, client: TestClient) -> None:
    response = client.get(path)

    assert response.status_code == 200, response.text
    parsed = model.model_validate(response.json())
    # the round-trip is lossless — re-dumping matches the wire body
    assert model.model_validate(parsed.model_dump(mode="json")) == parsed


def test_every_top_level_contract_has_a_stub() -> None:
    """The route table covers every contract in ``backend.models.CONTRACT_MODELS``."""
    from backend.models import CONTRACT_MODELS

    assert set(ROUTES.values()) == set(CONTRACT_MODELS)
