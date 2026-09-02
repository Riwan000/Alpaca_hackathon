"""``StrategyHypothesis`` and ``StrategyDecision`` contracts — task P1-BE-10.

``StrategyHypothesis`` is the standardized output every Strategy Agent produces
(BRD §16); ``StrategyDecision`` is the Strategy Manager's reasoned selection over
a set of them (BRD §18). A Strategy Agent may reject its own family, so
``viable=False`` is a first-class outcome and must carry a ``rejection_reason``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from backend.models.common import Contract, OptionLeg
from backend.models.enums import DecisionType, HedgeAction, StrategyType

__all__ = [
    "ComparisonRow",
    "HedgeMetrics",
    "PayoffPoint",
    "StrategyDecision",
    "StrategyHypothesis",
]


class HedgeMetrics(Contract):
    """Quantitative summary of a hypothesis — every number sourced from ``quant/``."""

    hedge_ratio: float | None = Field(default=None, ge=0)
    downside_protection_pct: float | None = None
    cost_pct_of_portfolio: float | None = Field(default=None, ge=0)
    net_delta: float | None = None
    net_gamma: float | None = None
    net_theta: float | None = None
    net_vega: float | None = None
    max_loss: float | None = None
    breakevens: list[float] = Field(default_factory=list)


class PayoffPoint(Contract):
    """One ``(underlying price, portfolio P&L)`` sample of the payoff curve."""

    price: float = Field(ge=0)
    pnl: float


class StrategyHypothesis(Contract):
    """A single strategy proposal from one Strategy Agent (BRD §16)."""

    cycle_id: str
    strategy: StrategyType
    action: HedgeAction
    viable: bool
    legs: list[OptionLeg] = Field(default_factory=list)
    cost: float = Field(ge=0, description="absolute premium/debit in account currency")
    hedge_metrics: HedgeMetrics = Field(default_factory=HedgeMetrics)
    payoff_profile: list[PayoffPoint] = Field(default_factory=list)
    liquidity: str | None = None
    risks: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    rationale: str
    rejection_conditions: list[str] = Field(
        default_factory=list, description="conditions under which this proposal stops being valid"
    )
    rejection_reason: str | None = Field(
        default=None, description="why the agent rejected its own family (viable is False)"
    )

    @model_validator(mode="after")
    def _reason_required_when_not_viable(self) -> StrategyHypothesis:
        if not self.viable and not (self.rejection_reason and self.rejection_reason.strip()):
            raise ValueError("rejection_reason is required when viable is False")
        return self


class ComparisonRow(Contract):
    """One row of the Strategy Manager's comparison table (BRD §17 step 2)."""

    strategy: StrategyType
    cost: float = Field(ge=0)
    downside_protection_pct: float | None = None
    upside_giveup_pct: float | None = None
    liquidity: str | None = None
    verdict: str | None = None
    score: float | None = None


class StrategyDecision(Contract):
    """The Strategy Manager's reasoned selection (BRD §18)."""

    cycle_id: str
    decision: DecisionType
    selected_strategy: StrategyType | None = None
    selected_hypothesis: StrategyHypothesis | None = None
    alternatives: list[StrategyHypothesis] = Field(default_factory=list)
    comparison: list[ComparisonRow] = Field(default_factory=list)
    rationale: str
    reassessment_conditions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _selection_matches_decision(self) -> StrategyDecision:
        if self.decision is DecisionType.SELECT_STRATEGY:
            if self.selected_strategy is None or self.selected_hypothesis is None:
                raise ValueError(
                    "SELECT_STRATEGY requires both selected_strategy and selected_hypothesis"
                )
            if self.selected_hypothesis.strategy is not self.selected_strategy:
                raise ValueError("selected_hypothesis.strategy must equal selected_strategy")
        return self
