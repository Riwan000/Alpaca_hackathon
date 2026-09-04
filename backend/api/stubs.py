"""Contract stub routers — task P1-BE-15.

Read-only endpoints that return a canonical fixture instance of each agent-state
contract. They let the frontend build against real, schema-valid payloads before
the agents that produce them exist, and they force every contract into the
OpenAPI document (task P1-BE-16).

Each route's ``response_model`` is the contract itself, so FastAPI validates the
fixture on the way out and publishes its JSON Schema under
``components.schemas``.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.models import (
    ExecutionPlan,
    HedgeContext,
    MonitoringState,
    RiskDecision,
    StrategyDecision,
    StrategyHypothesis,
)
from backend.models.examples import (
    EXAMPLE_EXECUTION_PLAN,
    EXAMPLE_HEDGE_CONTEXT,
    EXAMPLE_MONITORING_STATE,
    EXAMPLE_RISK_DECISION,
    EXAMPLE_STRATEGY_DECISION,
    EXAMPLE_STRATEGY_HYPOTHESIS,
)

router = APIRouter(tags=["stubs"])


@router.get("/context", response_model=HedgeContext)
def stub_context() -> HedgeContext:
    """A fully-populated :class:`HedgeContext` fixture (BRD §14)."""
    return EXAMPLE_HEDGE_CONTEXT


@router.get("/strategy/hypothesis", response_model=StrategyHypothesis)
def stub_strategy_hypothesis() -> StrategyHypothesis:
    """A single viable :class:`StrategyHypothesis` fixture (BRD §16)."""
    return EXAMPLE_STRATEGY_HYPOTHESIS


@router.get("/strategy", response_model=StrategyDecision)
def stub_strategy() -> StrategyDecision:
    """A :class:`StrategyDecision` fixture selecting the protective put (BRD §18)."""
    return EXAMPLE_STRATEGY_DECISION


@router.get("/risk", response_model=RiskDecision)
def stub_risk() -> RiskDecision:
    """An APPROVE :class:`RiskDecision` fixture (BRD §20)."""
    return EXAMPLE_RISK_DECISION


@router.get("/execution/plan", response_model=ExecutionPlan)
def stub_execution_plan() -> ExecutionPlan:
    """A ready-to-submit :class:`ExecutionPlan` fixture (BRD §21)."""
    return EXAMPLE_EXECUTION_PLAN


@router.get("/monitoring", response_model=MonitoringState)
def stub_monitoring() -> MonitoringState:
    """A :class:`MonitoringState` fixture recommending reassessment (BRD §24)."""
    return EXAMPLE_MONITORING_STATE
