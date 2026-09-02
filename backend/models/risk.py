"""``RiskDecision`` contract — task P1-BE-11 (BRD §19–§20).

Output of the non-negotiable safety gate. The LLM Risk Agent may not override a
deterministic failure, so a ``REJECT`` must name at least one violation and a
``MODIFY`` must carry at least one concrete modification. Field names line up
with the ``risk_checks`` table (migration 0007): ``checks`` / ``violations`` /
``warnings`` / ``modifications``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from backend.models.common import Contract
from backend.models.enums import RiskVerdict
from backend.models.strategy import StrategyHypothesis

__all__ = ["RiskCheck", "RiskDecision", "RiskModification"]


class RiskCheck(Contract):
    """One deterministic check with its pass/fail result and the numbers behind it."""

    name: str
    category: str = Field(
        description="PORTFOLIO | POSITION_LIMITS | COST | OPTIONS | EXECUTION"
    )
    passed: bool
    detail: str | None = None
    observed: float | None = None
    limit: float | None = None


class RiskModification(Contract):
    """A permitted adjustment the Risk Agent proposes instead of rejecting (BRD §20)."""

    field: str
    from_value: float | str | None = None
    to_value: float | str | None = None
    reason: str


class RiskDecision(Contract):
    """Structured pass/fail with per-check reasons (BRD §20)."""

    cycle_id: str
    verdict: RiskVerdict
    checks: list[RiskCheck] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    modifications: list[RiskModification] = Field(default_factory=list)
    rationale: str
    approved_hypothesis: StrategyHypothesis | None = Field(
        default=None, description="the (possibly modified) hypothesis cleared for execution"
    )

    @model_validator(mode="after")
    def _verdict_consistency(self) -> RiskDecision:
        if self.verdict is RiskVerdict.REJECT and not self.violations:
            raise ValueError("a REJECT verdict must list at least one violation")
        if self.verdict is RiskVerdict.MODIFY and not self.modifications:
            raise ValueError("a MODIFY verdict must carry at least one modification")
        if self.verdict is RiskVerdict.APPROVE and self.violations:
            raise ValueError("an APPROVE verdict cannot carry violations")
        return self
