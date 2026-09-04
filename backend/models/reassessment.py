"""``ReassessmentDecision`` / ``ReassessmentRequest`` contracts — task P7-BE-6 (BRD §28).

Level-2 intelligent reassessment is what closes the adaptive loop: once a
Level-1 monitoring trigger fires (:mod:`backend.agents.monitoring.agent`), the
Reassessment Agent decides what to *do* about the hedge already on the book —
keep it, size it up or down, swap it, or take it off.

``ReassessmentDecision.outcome`` reuses :class:`~backend.models.enums.HedgeAction`
but is constrained to the six adaptive-lifecycle values (BRD §28):

    MAINTAIN | INCREASE | DECREASE | REMOVE | REPLACE | NO_TRADE

``NEW_HEDGE`` is deliberately excluded — a reassessment always acts relative to
an existing position; opening a fresh hedge from nothing is the Strategy
Manager's job (Phase 4), not the Reassessment Agent's.

``ReassessmentRequest`` is the small payload a fired trigger carries back into
the orchestrator (task P7-BE-5): the trigger reason plus the current hedge, so
``STRATEGY_EVALUATION`` re-enters with the context it needs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from backend.models.common import Contract
from backend.models.enums import HedgeAction, TriggerType
from backend.models.hedge_context import CurrentHedge

__all__ = [
    "REASSESSMENT_OUTCOMES",
    "ReassessmentDecision",
    "ReassessmentRequest",
]

#: The adaptive-lifecycle outcomes a Level-2 reassessment may return (BRD §28).
#: ``HedgeAction.NEW_HEDGE`` is not here — a reassessment acts on an existing
#: hedge; a brand-new one is the Strategy Manager's decision.
REASSESSMENT_OUTCOMES: frozenset[HedgeAction] = frozenset(
    {
        HedgeAction.MAINTAIN,
        HedgeAction.INCREASE,
        HedgeAction.DECREASE,
        HedgeAction.REMOVE,
        HedgeAction.REPLACE,
        HedgeAction.NO_TRADE,
    }
)

#: Outcomes that change the position on the book and therefore need an
#: apply-change plan through the risk gate (task P7-BE-7).
CHANGE_OUTCOMES: frozenset[HedgeAction] = frozenset(
    {HedgeAction.DECREASE, HedgeAction.REMOVE, HedgeAction.REPLACE}
)


class ReassessmentRequest(Contract):
    """What a fired Level-1 trigger carries into a Level-2 reassessment cycle.

    Threaded onto the orchestrator state as ``reassessment`` so
    ``STRATEGY_EVALUATION`` re-enters knowing *why* it was woken and *what* is
    already hedged (task P7-BE-5).
    """

    cycle_id: str
    triggered_at: datetime
    trigger_types: list[TriggerType] = Field(default_factory=list)
    reason: str
    current_hedge: CurrentHedge = Field(default_factory=CurrentHedge)
    emergency: bool = False
    bypassed_cooldown: bool = False


class ReassessmentDecision(Contract):
    """The Reassessment Agent's schema-bound verdict on an existing hedge (BRD §28)."""

    cycle_id: str
    outcome: HedgeAction
    rationale: str
    trigger_types: list[TriggerType] = Field(default_factory=list)
    current_hedge_ratio: float | None = Field(default=None, ge=0)
    target_hedge_ratio: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _outcome_in_scope(self) -> ReassessmentDecision:
        if self.outcome not in REASSESSMENT_OUTCOMES:
            raise ValueError(
                f"reassessment outcome {self.outcome.value!r} is out of scope; "
                f"expected one of {sorted(a.value for a in REASSESSMENT_OUTCOMES)}"
            )
        return self

    @property
    def changes_position(self) -> bool:
        """``True`` when the outcome needs an apply-change plan (DECREASE/REMOVE/REPLACE)."""
        return self.outcome in CHANGE_OUTCOMES
