"""Level-2 intelligent reassessment — tasks P7-BE-5, P7-BE-6, P7-BE-8 (BRD §28).

The Level-1 :class:`~backend.agents.monitoring.agent.MonitoringAgent` only
*detects* — it never trades. This module is the escalation:

* :func:`should_escalate` — the gate between Level 1 and Level 2. It takes the
  fired :class:`~backend.models.monitoring.TriggerObservation`\\ s (typically the
  deadband-filtered set from :func:`backend.agents.monitoring.triggers.apply_deadband`,
  or the ``trigger_history`` on a :class:`~backend.models.monitoring.MonitoringState`)
  plus the post-adjustment ``cooldown_until``: a normal trigger inside the
  cooldown window is suppressed, an ``is_emergency`` one
  (:func:`backend.agents.monitoring.triggers.evaluate_emergency`) bypasses it
  (task P7-BE-4 / P7-BE-10).
* :class:`ReassessmentAgent` — given the hedge context and the monitoring
  snapshot, returns a schema-bound :class:`~backend.models.reassessment.ReassessmentDecision`
  whose ``outcome`` is one of ``MAINTAIN`` / ``INCREASE`` / ``DECREASE`` /
  ``REMOVE`` / ``REPLACE`` / ``NO_TRADE`` (task P7-BE-6). The LLM only labels the
  situation; a deterministic heuristic fallback fires whenever the model is
  unavailable or off-schema, so a reassessment always resolves.

The apply-change path for a position-changing outcome (``DECREASE`` / ``REMOVE``
/ ``REPLACE``) lives in :mod:`backend.agents.monitoring.apply_change`; re-entering
the orchestrator graph at ``STRATEGY_EVALUATION`` lives in
:mod:`backend.agents.monitoring.escalation`.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from openai import OpenAI

from backend.agents.base import AgentError, complete_json
from backend.models.enums import HedgeAction, TriggerType
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState, TriggerObservation
from backend.models.reassessment import (
    REASSESSMENT_OUTCOMES,
    ReassessmentDecision,
    ReassessmentRequest,
)

__all__ = [
    "EscalationDecision",
    "ReassessmentAgent",
    "build_reassessment_request",
    "should_escalate",
]

logger = logging.getLogger(__name__)

# Deterministic-fallback thresholds — a "stabilization" shape (volatility back
# down, drawdown recovered) means the book needs *less* protection.
_STABLE_VOL = 0.20
_CALM_VOL = 0.14
_RECOVERED_DRAWDOWN = 0.02
_FLAT_DRAWDOWN = 0.01
_STABLE_VIX = 20.0
_DEEPENING_DRAWDOWN = 0.06

_SYSTEM_PROMPT = (
    "You are the Reassessment Agent for an autonomous portfolio-hedging system. "
    "A monitoring trigger has fired on a portfolio that already carries a hedge. "
    "Decide what to do with the EXISTING hedge. Respond with a single JSON object: "
    '{"outcome": one of ["MAINTAIN","INCREASE","DECREASE","REMOVE","REPLACE","NO_TRADE"], '
    '"rationale": "<one sentence>", "confidence": <0..1>}. '
    "MAINTAIN = leave it; INCREASE = add protection; DECREASE = trim it; "
    "REMOVE = close it entirely; REPLACE = close and re-open a better-fitted hedge; "
    "NO_TRADE = nothing actionable. Never invent a brand-new hedge from nothing."
)


@dataclasses.dataclass(frozen=True)
class EscalationDecision:
    """Whether a fired Level-1 trigger should start a Level-2 reassessment."""

    escalate: bool
    emergency: bool
    bypassed_cooldown: bool
    reason: str


def _as_observations(
    triggers: Sequence[TriggerObservation] | MonitoringState,
) -> tuple[list[TriggerObservation], datetime | None, bool]:
    """Normalize either input shape to ``(observations, cooldown_until, in_cooldown)``.

    Accepts the deadband-filtered ``list[TriggerObservation]`` from
    :mod:`backend.agents.monitoring.triggers`, or a :class:`MonitoringState`
    (its ``trigger_history``, falling back to synthesizing bare observations
    from ``active_triggers`` for a state that only carries the enum list).
    """
    if isinstance(triggers, MonitoringState):
        obs = list(triggers.trigger_history) or [
            TriggerObservation(trigger_type=t, observed_at=triggers.as_of)
            for t in triggers.active_triggers
        ]
        return obs, triggers.cooldown_until, triggers.in_cooldown
    return list(triggers), None, False


def should_escalate(
    triggers: Sequence[TriggerObservation] | MonitoringState,
    *,
    cooldown_until: datetime | None = None,
    now: datetime | None = None,
) -> EscalationDecision:
    """Gate Level 1 → Level 2 (task P7-BE-8, cooldown per P7-BE-4).

    ``triggers`` is the fired (ideally deadband-filtered) observation set — a
    plain list from :func:`backend.agents.monitoring.triggers.apply_deadband`,
    or a :class:`MonitoringState` (its ``trigger_history`` / ``cooldown_until``).
    An explicit ``cooldown_until`` overrides one carried on a ``MonitoringState``.

    * No fired trigger → no escalation.
    * A trigger while a cooldown is in force → suppressed, **unless** it carries
      ``is_emergency=True`` (:func:`backend.agents.monitoring.triggers.evaluate_emergency`
      — a hard drawdown breach or a volatility/VIX blow-out), which bypasses it.
    * Otherwise → escalate.
    """
    now = now or datetime.now(timezone.utc)
    obs, state_cooldown, state_in_cooldown = _as_observations(triggers)
    until = cooldown_until if cooldown_until is not None else state_cooldown

    if not obs:
        return EscalationDecision(
            escalate=False, emergency=False, bypassed_cooldown=False,
            reason="no triggers fired",
        )

    emergency_obs = [o for o in obs if o.is_emergency]
    emergency = bool(emergency_obs)
    in_cooldown = state_in_cooldown or (until is not None and until > now)

    if in_cooldown and not emergency:
        return EscalationDecision(
            escalate=False,
            emergency=False,
            bypassed_cooldown=False,
            reason=(
                f"suppressed by cooldown until {until:%Y-%m-%d %H:%M:%S}"
                if until
                else "suppressed by cooldown"
            ),
        )

    types = [o.trigger_type.value for o in (emergency_obs or obs)]
    return EscalationDecision(
        escalate=True,
        emergency=emergency,
        bypassed_cooldown=in_cooldown and emergency,
        reason=(
            "emergency trigger bypassed cooldown"
            if (in_cooldown and emergency)
            else f"trigger(s) {types} → reassess"
        ),
    )


def build_reassessment_request(
    context: HedgeContext,
    state: MonitoringState,
    *,
    escalation: EscalationDecision | None = None,
) -> ReassessmentRequest:
    """Package the trigger reason + current hedge for a Level-2 cycle (task P7-BE-5)."""
    esc = escalation or should_escalate(state)
    triggers = list(state.active_triggers)
    reason_bits = [obs.detail for obs in state.trigger_history if obs.detail]
    reason = "; ".join(reason_bits) or esc.reason
    return ReassessmentRequest(
        cycle_id=context.cycle_id,
        triggered_at=state.as_of,
        trigger_types=triggers,
        reason=reason,
        current_hedge=context.current_hedge,
        emergency=esc.emergency,
        bypassed_cooldown=esc.bypassed_cooldown,
    )


class ReassessmentAgent:
    """Level-2 reasoning over an existing hedge (task P7-BE-6, BRD §28).

    ::

        agent    = ReassessmentAgent()
        decision = agent.assess(hedge_context, monitoring_state)
    """

    def __init__(self, *, client: OpenAI | None = None) -> None:
        self._client = client

    def assess(
        self,
        context: HedgeContext,
        state: MonitoringState,
        *,
        client: OpenAI | None = None,
    ) -> ReassessmentDecision:
        """Return the schema-bound :class:`ReassessmentDecision`.

        The LLM classifies the situation; any failure (no key, timeout,
        off-schema output) falls back to :meth:`_heuristic`, so the call always
        yields a valid decision.
        """
        if client is not None:
            self._client = client

        triggers = list(state.active_triggers)
        try:
            parsed = complete_json(
                _SYSTEM_PROMPT,
                self._context_block(context, state),
                client=self._client,
            )
            outcome = self._parse_outcome(parsed.get("outcome"))
            rationale = str(parsed.get("rationale", "")).strip() or (
                f"Reassessment after {[t.value for t in triggers]}."
            )
            confidence = self._parse_confidence(parsed.get("confidence"))
        except (AgentError, ValueError) as exc:
            logger.warning(
                "ReassessmentAgent.assess: LLM path unavailable (%s); using heuristic",
                exc,
            )
            return self._heuristic(context, state)

        return ReassessmentDecision(
            cycle_id=context.cycle_id,
            outcome=outcome,
            rationale=rationale,
            trigger_types=triggers,
            current_hedge_ratio=context.current_hedge.hedge_ratio,
            target_hedge_ratio=(
                context.current_hedge.target_hedge_ratio
                if context.current_hedge.target_hedge_ratio is not None
                else context.objective.target_hedge_ratio
            ),
            confidence=confidence,
        )

    # ------------------------------------------------------------------ #
    # deterministic fallback
    # ------------------------------------------------------------------ #

    def _heuristic(
        self, context: HedgeContext, state: MonitoringState
    ) -> ReassessmentDecision:
        """Rule-based outcome when the LLM is unavailable (BRD §28)."""
        triggers = set(state.active_triggers)
        hedge = context.current_hedge
        pf = context.portfolio_state
        vol = pf.volatility
        drawdown = abs(pf.drawdown) if pf.drawdown is not None else None
        vix = context.market_state.vix if context.market_state else None

        def decide() -> tuple[HedgeAction, str]:
            if not hedge.active:
                return HedgeAction.NO_TRADE, "no hedge on the book to reassess"

            if TriggerType.CORRELATION_BREAKDOWN in triggers:
                return (
                    HedgeAction.REPLACE,
                    "correlation breakdown — the current hedge no longer tracks the book",
                )

            deepening = (
                (drawdown is not None and drawdown >= _DEEPENING_DRAWDOWN)
                or (vol is not None and vol >= _STABLE_VOL + 0.10)
            )
            if deepening and (
                triggers & {TriggerType.DRAWDOWN_LIMIT, TriggerType.VOLATILITY_SPIKE}
            ):
                return (
                    HedgeAction.INCREASE,
                    "drawdown / volatility still deepening — add protection",
                )

            if triggers == {TriggerType.TIME_ELAPSED}:
                return (
                    HedgeAction.REPLACE,
                    "hedge near expiration — roll into a fresh contract",
                )

            stabilizing = (
                (vol is None or vol < _STABLE_VOL)
                and (drawdown is None or drawdown < _RECOVERED_DRAWDOWN)
                and (vix is None or vix < _STABLE_VIX)
            )
            if stabilizing:
                fully_calm = (
                    (vol is not None and vol < _CALM_VOL)
                    and (drawdown is not None and drawdown < _FLAT_DRAWDOWN)
                )
                if fully_calm:
                    return (
                        HedgeAction.REMOVE,
                        "market stabilized — protection no longer earning its cost",
                    )
                return (
                    HedgeAction.DECREASE,
                    "conditions easing — trim the hedge toward the lower target",
                )

            return HedgeAction.MAINTAIN, "no decisive change — hold the current hedge"

        outcome, rationale = decide()
        return ReassessmentDecision(
            cycle_id=context.cycle_id,
            outcome=outcome,
            rationale=f"Deterministic fallback: {rationale}.",
            trigger_types=list(state.active_triggers),
            current_hedge_ratio=hedge.hedge_ratio,
            target_hedge_ratio=(
                hedge.target_hedge_ratio
                if hedge.target_hedge_ratio is not None
                else context.objective.target_hedge_ratio
            ),
            confidence=0.5,
        )

    # ------------------------------------------------------------------ #
    # parsing helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_outcome(raw: object) -> HedgeAction:
        try:
            outcome = HedgeAction(str(raw).strip().upper())
        except ValueError as exc:
            raise ValueError(f"unknown reassessment outcome {raw!r}") from exc
        if outcome not in REASSESSMENT_OUTCOMES:
            raise ValueError(f"outcome {outcome.value!r} is out of reassessment scope")
        return outcome

    @staticmethod
    def _parse_confidence(raw: object) -> float | None:
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, value))

    @staticmethod
    def _context_block(context: HedgeContext, state: MonitoringState) -> str:
        pf = context.portfolio_state
        hedge = context.current_hedge
        lines = [
            "=== Fired triggers ===",
            ", ".join(t.value for t in state.active_triggers) or "(none)",
            "",
            "=== Trigger detail ===",
        ]
        lines += [f"  - {obs.detail}" for obs in state.trigger_history if obs.detail] or [
            "  (no detail)"
        ]
        lines += [
            "",
            "=== Current hedge ===",
            f"active={hedge.active} strategy={getattr(hedge.strategy_type, 'value', None)} "
            f"hedge_ratio={hedge.hedge_ratio} target={hedge.target_hedge_ratio} "
            f"pnl={hedge.hedge_pnl} expiration={hedge.expiration}",
            "",
            "=== Portfolio ===",
            f"total_value={pf.total_value} drawdown={pf.drawdown} volatility={pf.volatility} "
            f"gross_exposure={pf.gross_exposure} beta={pf.beta}",
            f"vix={context.market_state.vix if context.market_state else None} "
            f"regime={context.market_state.regime if context.market_state else None}",
            f"drawdown_tolerance={context.objective.drawdown_tolerance_pct} "
            f"max_hedge_budget={context.objective.max_hedge_budget_pct}",
        ]
        return "\n".join(lines)
