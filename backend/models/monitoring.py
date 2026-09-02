"""``MonitoringState`` contract — task P1-BE-13 (BRD §24–§27).

The Monitoring Agent makes no trades; it tracks whether the portfolio / hedge
has drifted enough to warrant reassessment. ``trigger_history`` is a typed list
of past observations and ``cooldown_until`` is optional — it is set only after a
hedge adjustment, and minor signals inside that window are ignored (BRD §27).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from backend.models.common import Contract
from backend.models.enums import TriggerType

__all__ = ["MonitoringState", "TriggerObservation"]


class TriggerObservation(Contract):
    """One evaluated trigger — what was observed against its threshold."""

    trigger_type: TriggerType
    observed_at: datetime
    observed_value: float | None = None
    threshold: float | None = None
    detail: str | None = None
    breached: bool = True


class MonitoringState(Contract):
    """Rolling monitoring snapshot for one cycle (BRD §24)."""

    cycle_id: str
    as_of: datetime
    portfolio_value: float | None = None
    drawdown: float | None = None
    volatility: float | None = Field(default=None, ge=0)
    gross_exposure: float | None = None
    hedge_ratio: float | None = Field(default=None, ge=0)
    target_hedge_ratio: float | None = Field(default=None, ge=0)
    hedge_pnl: float | None = None
    time_to_expiration_days: float | None = None
    trigger_history: list[TriggerObservation] = Field(default_factory=list)
    active_triggers: list[TriggerType] = Field(default_factory=list)
    cooldown_until: datetime | None = None
    in_cooldown: bool = False
    reassessment_recommended: bool = False

    @model_validator(mode="after")
    def _cooldown_flag_consistency(self) -> MonitoringState:
        if self.in_cooldown and self.cooldown_until is None:
            raise ValueError("in_cooldown is True but cooldown_until is not set")
        return self
