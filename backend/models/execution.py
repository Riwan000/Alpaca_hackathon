"""``ExecutionPlan`` and ``ExecutionResult`` contracts — task P1-BE-12.

``ExecutionPlan`` is what the Execution Agent receives for an already-approved
decision (BRD §21): approval id, strategy, legs, order constraints, price
tolerance. Multi-leg structures must be submitted as one combo order to avoid
legging risk (BRD §22). ``ExecutionResult`` is the truthful terminal report
(BRD §23) — a partial fill must never be reported as ``FILLED``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from backend.models.common import Contract, OptionLeg
from backend.models.enums import ExecutionStatus, StrategyType

__all__ = [
    "ExecutionPlan",
    "ExecutionResult",
    "FailedLeg",
    "FilledLeg",
    "OrderConstraints",
]

_MULTI_LEG_CLASSES = frozenset({"MLEG", "COMBO"})


class OrderConstraints(Contract):
    """Order-level constraints and the pre-flight price band (BRD §21)."""

    time_in_force: str = "DAY"
    order_type: str = "LIMIT"
    limit_price: float | None = Field(default=None, ge=0)
    price_tolerance_pct: float = Field(default=0.05, ge=0, le=1)
    allow_legging: bool = Field(
        default=False, description="permit independent legs when a combo order is unsupported"
    )


class ExecutionPlan(Contract):
    """A ready-to-submit plan built from an approved :class:`RiskDecision`."""

    cycle_id: str
    approval_id: str = Field(description="id of the RiskDecision that approved this plan")
    strategy: StrategyType
    legs: list[OptionLeg] = Field(min_length=1)
    order_class: str = Field(default="MLEG", description="MLEG/COMBO for multi-leg, SINGLE otherwise")
    constraints: OrderConstraints = Field(default_factory=OrderConstraints)
    estimated_cost: float = Field(ge=0)

    @model_validator(mode="after")
    def _multi_leg_uses_combo_class(self) -> ExecutionPlan:
        if len(self.legs) > 1 and self.order_class not in _MULTI_LEG_CLASSES:
            raise ValueError(
                "a multi-leg plan must use order_class 'MLEG' or 'COMBO' (legging risk, BRD §22)"
            )
        return self


class FilledLeg(Contract):
    """A leg that filled, with realized price and slippage vs the expected price."""

    leg_symbol: str
    qty: int = Field(gt=0)
    price: float = Field(ge=0)
    filled_at: datetime
    slippage: float | None = None


class FailedLeg(Contract):
    """A leg that did not fill, with the reason."""

    leg_symbol: str
    reason: str


class ExecutionResult(Contract):
    """Truthful terminal report of an execution attempt (BRD §23)."""

    cycle_id: str
    status: ExecutionStatus
    order_ids: list[str] = Field(default_factory=list)
    broker_order_id: str | None = None
    filled_legs: list[FilledLeg] = Field(default_factory=list)
    failed_legs: list[FailedLeg] = Field(default_factory=list)
    actual_cost: float | None = None
    slippage: float | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _status_matches_legs(self) -> ExecutionResult:
        if self.status is ExecutionStatus.FILLED and self.failed_legs:
            raise ValueError("a FILLED result cannot carry failed_legs")
        if self.status is ExecutionStatus.PARTIALLY_FILLED and not self.failed_legs:
            raise ValueError("a PARTIALLY_FILLED result must record the unfilled leg(s)")
        if self.status is ExecutionStatus.FAILED and not (self.error and self.error.strip()):
            raise ValueError("a FAILED result must carry an error message")
        return self
