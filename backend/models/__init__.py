"""Agent-state contracts — tasks P1-BE-9 … P1-BE-14 (BRD §30).

The interface objects that pass between agents::

    HedgeContext -> StrategyHypothesis[] -> StrategyDecision -> RiskDecision
                 -> ExecutionPlan -> ExecutionResult -> MonitoringState

Every model is strict and immutable (see :class:`backend.models.common.Contract`).
Import the contract you need straight from this package.
"""

from __future__ import annotations

from backend.models.common import Contract, OptionLeg, PortfolioPosition
from backend.models.enums import (
    AssetClass,
    DecisionType,
    ExecutionStatus,
    HedgeAction,
    OptionRight,
    OrderSide,
    OrderStatus,
    RiskVerdict,
    StrategyType,
    TriggerType,
)
from backend.models.execution import (
    ExecutionPlan,
    ExecutionResult,
    FailedLeg,
    FilledLeg,
    OrderConstraints,
)
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    NewsItem,
    OptionCandidate,
    PortfolioState,
    StockView,
)
from backend.models.monitoring import MonitoringState, TriggerObservation
from backend.models.risk import RiskCheck, RiskDecision, RiskModification
from backend.models.strategy import (
    ComparisonRow,
    HedgeMetrics,
    PayoffPoint,
    StrategyDecision,
    StrategyHypothesis,
)

# The top-level contracts exchanged between agents, in pipeline order. The stub
# routers (P1-BE-15) and the OpenAPI artifact (P1-BE-16) iterate this so a new
# contract is exposed and schema-checked the moment it is added here.
CONTRACT_MODELS: tuple[type[Contract], ...] = (
    HedgeContext,
    StrategyHypothesis,
    StrategyDecision,
    RiskDecision,
    ExecutionPlan,
    ExecutionResult,
    MonitoringState,
)

__all__ = [
    # registry
    "CONTRACT_MODELS",
    # base + shared
    "Contract",
    "OptionLeg",
    "PortfolioPosition",
    # enums
    "AssetClass",
    "DecisionType",
    "ExecutionStatus",
    "HedgeAction",
    "OptionRight",
    "OrderSide",
    "OrderStatus",
    "RiskVerdict",
    "StrategyType",
    "TriggerType",
    # hedge context
    "CurrentHedge",
    "HedgeContext",
    "HedgeObjective",
    "MarketState",
    "NewsItem",
    "OptionCandidate",
    "PortfolioState",
    "StockView",
    # strategy
    "ComparisonRow",
    "HedgeMetrics",
    "PayoffPoint",
    "StrategyDecision",
    "StrategyHypothesis",
    # risk
    "RiskCheck",
    "RiskDecision",
    "RiskModification",
    # execution
    "ExecutionPlan",
    "ExecutionResult",
    "FailedLeg",
    "FilledLeg",
    "OrderConstraints",
    # monitoring
    "MonitoringState",
    "TriggerObservation",
]
