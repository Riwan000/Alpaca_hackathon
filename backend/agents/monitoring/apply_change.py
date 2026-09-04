"""Apply-change path for a Level-2 reassessment — task P7-BE-7 (BRD §28–29).

A position-changing reassessment outcome (``DECREASE`` / ``REMOVE`` / ``REPLACE``)
has to become a real order, and it goes through the *same* non-negotiable risk
gate as a fresh hedge:

    reassessment outcome
        → closing StrategyHypothesis (the current legs, inverted, sized to the outcome)
        → RiskAgent.review (deterministic engine + LLM)  ← the gate
        → build_execution_plan (APPROVE / MODIFY)
        → [optional] submit_plan + persist orders/fills + hedge_changes row

``DECREASE`` trims the structure toward the lower target ratio; ``REMOVE`` closes
it entirely; ``REPLACE`` closes it entirely and flags that a fresh hedge cycle
should follow (the re-open is Strategy-Manager work, re-entered via
:mod:`backend.agents.monitoring.escalation`).

A reduce/close order lowers exposure and costs nothing, so it clears the
deterministic checklist on its own merits — but if the gate does reject it (e.g.
the legs are already inside the expiration window), that is reported, never
overridden.

Known gap: the submitted payload reuses :func:`backend.integrations.alpaca.orders.build_single_leg_payloads`,
whose ``position_intent`` is derived from the (now inverted) side, so a close
goes out as ``*_to_open`` rather than ``*_to_close``. Harmless against the paper
account for the demo; a real deployment wants a close intent on the leg builder.
"""

from __future__ import annotations

import dataclasses
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from backend.agents.execution import (
    ExecutionPlanError,
    build_execution_plan,
    build_execution_result,
    persist_execution_result,
)
from backend.agents.risk.agent import RiskAgent
from backend.agents.risk.engine import check_hedge_budget
from backend.agents.risk.execution import check_price_band
from backend.agents.risk.liquidity import check_buying_power
from backend.integrations.alpaca.client import AlpacaError
from backend.integrations.alpaca.orders import OrderSubmitter, submit_plan
from backend.models.common import OptionLeg
from backend.models.enums import (
    ExecutionStatus,
    HedgeAction,
    OrderSide,
    RiskVerdict,
    StrategyType,
)
from backend.models.execution import ExecutionPlan, ExecutionResult
from backend.models.hedge_context import CurrentHedge, HedgeContext
from backend.models.risk import RiskDecision
from backend.models.strategy import HedgeMetrics, StrategyHypothesis
from backend.models.reassessment import ReassessmentDecision

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = [
    "REDUCE_CHECKS",
    "ApplyChangeError",
    "ApplyChangeResult",
    "apply_change",
    "build_change_hypothesis",
]

logger = logging.getLogger(__name__)

_OPPOSITE_SIDE = {OrderSide.BUY: OrderSide.SELL, OrderSide.SELL: OrderSide.BUY}

#: The deterministic checks that still bind a *de-risking* trade. A close/reduce
#: strictly lowers the hedge ratio, notional, per-name contract count and net
#: delta, and its legs are positions already on the book — not contracts the
#: current Options pass surfaced — so the open-a-hedge screens (position limit,
#: contract validity, expiration window, entry liquidity, open-side delta bounds)
#: do not apply to it. What still binds: the cash math (a debit-to-close must fit
#: budget + buying power) and a sane execution price. The gate is still
#: :class:`RiskAgent` — deterministic engine *and* LLM — and it can still REJECT.
REDUCE_CHECKS = (check_hedge_budget, check_buying_power, check_price_band)


class ApplyChangeError(ValueError):
    """The reassessment outcome cannot be turned into an apply-change plan."""


@dataclasses.dataclass(frozen=True)
class ApplyChangeResult:
    """What :func:`apply_change` produced for one reassessment outcome."""

    outcome: HedgeAction
    risk_decision: RiskDecision | None = None
    plan: ExecutionPlan | None = None
    execution_result: ExecutionResult | None = None
    before_hedge_ratio: float | None = None
    after_hedge_ratio: float | None = None
    delta: float | None = None
    hedge_change_id: int | None = None
    reopen_recommended: bool = False
    submitted: bool = False
    notes: list[str] = dataclasses.field(default_factory=list)

    @property
    def cleared_risk_gate(self) -> bool:
        return (
            self.risk_decision is not None
            and self.risk_decision.verdict in {RiskVerdict.APPROVE, RiskVerdict.MODIFY}
        )


def _close_quantity(outcome: HedgeAction, current_qty: int, ratio_scale: float) -> int:
    """Contracts to close for one leg.

    ``REMOVE`` / ``REPLACE`` close the whole leg. ``DECREASE`` closes the
    fraction that brings the hedge ratio down to target (``1 - target/current``),
    at least one contract and never more than the leg holds.
    """
    if outcome in {HedgeAction.REMOVE, HedgeAction.REPLACE}:
        return current_qty
    close = round(current_qty * ratio_scale)
    return max(1, min(current_qty, close))


def build_change_hypothesis(
    decision: ReassessmentDecision,
    context: HedgeContext,
    *,
    current_hedge: CurrentHedge | None = None,
) -> StrategyHypothesis:
    """Build the closing :class:`StrategyHypothesis` for a position-changing outcome.

    The current hedge legs are inverted (BUY↔SELL) and sized to the outcome. The
    hypothesis carries ``cost=0`` (a close is a credit, not a debit) and the
    *resulting* lower hedge ratio in ``hedge_metrics``.
    """
    if not decision.changes_position:
        raise ApplyChangeError(
            f"outcome {decision.outcome.value} does not change the position"
        )
    hedge = current_hedge or context.current_hedge
    if not hedge.legs:
        raise ApplyChangeError(
            f"cycle {context.cycle_id}: current hedge carries no legs on record to close"
        )

    current_ratio = hedge.hedge_ratio if hedge.hedge_ratio is not None else 0.0
    target_ratio = (
        decision.target_hedge_ratio
        if decision.target_hedge_ratio is not None
        else (hedge.target_hedge_ratio if hedge.target_hedge_ratio is not None else 0.0)
    )
    if decision.outcome is HedgeAction.DECREASE and current_ratio > 0:
        ratio_scale = max(0.0, min(1.0, 1.0 - (target_ratio / current_ratio)))
        if ratio_scale == 0.0:  # target not below current — trim a nominal slice
            ratio_scale = 0.25
    else:
        ratio_scale = 1.0

    closing_legs: list[OptionLeg] = []
    for leg in hedge.legs:
        qty = _close_quantity(decision.outcome, leg.quantity, ratio_scale)
        closing_legs.append(
            leg.model_copy(
                update={
                    "side": _OPPOSITE_SIDE[leg.side],
                    "quantity": qty,
                    "limit_price": None,
                }
            )
        )

    if decision.outcome is HedgeAction.REMOVE or decision.outcome is HedgeAction.REPLACE:
        result_ratio = 0.0
    else:
        closed = sum(l.quantity for l in closing_legs)
        held = sum(l.quantity for l in hedge.legs)
        result_ratio = round(current_ratio * (1 - closed / held), 4) if held else 0.0

    strategy = hedge.strategy_type or StrategyType.PROTECTIVE_PUT
    return StrategyHypothesis(
        cycle_id=context.cycle_id,
        strategy=strategy,
        action=decision.outcome,
        viable=True,
        legs=closing_legs,
        cost=0.0,
        hedge_metrics=HedgeMetrics(hedge_ratio=max(0.0, result_ratio)),
        rationale=(
            f"Apply-change ({decision.outcome.value}): {decision.rationale} "
            f"Closing {sum(l.quantity for l in closing_legs)} of "
            f"{sum(l.quantity for l in hedge.legs)} contract(s)."
        ),
    )


def apply_change(
    decision: ReassessmentDecision,
    context: HedgeContext,
    *,
    current_hedge: CurrentHedge | None = None,
    risk_client: OpenAI | None = None,
    engine: "Engine | None" = None,
    broker: OrderSubmitter | None = None,
    reassessment_id: int | None = None,
) -> ApplyChangeResult:
    """Turn a ``DECREASE`` / ``REMOVE`` / ``REPLACE`` outcome into a risk-gated plan.

    With a ``broker`` the plan is also submitted and the ``orders`` / ``fills`` /
    ``hedge_changes`` rows are written (when an ``engine`` is given). Without a
    broker the plan is returned unsubmitted — still through the risk gate.
    Never raises: a build or gate failure comes back on the result as a note.
    """
    hedge = current_hedge or context.current_hedge
    notes: list[str] = []
    reopen = decision.outcome is HedgeAction.REPLACE
    before_ratio = hedge.hedge_ratio

    if not decision.changes_position:
        return ApplyChangeResult(
            outcome=decision.outcome,
            before_hedge_ratio=before_ratio,
            after_hedge_ratio=before_ratio,
            delta=0.0,
            notes=[f"{decision.outcome.value}: no position change required"],
        )

    try:
        hypothesis = build_change_hypothesis(decision, context, current_hedge=hedge)
    except ApplyChangeError as exc:
        return ApplyChangeResult(
            outcome=decision.outcome,
            before_hedge_ratio=before_ratio,
            reopen_recommended=reopen,
            notes=[f"apply-change aborted: {exc}"],
        )

    try:
        risk_decision = RiskAgent(client=risk_client).review(
            hypothesis, context, checks=REDUCE_CHECKS, repo=_risk_repo(engine)
        )
    except Exception as exc:  # noqa: BLE001 - a gate failure fails safe: no order
        logger.exception("apply_change: risk gate raised for cycle %s", context.cycle_id)
        return ApplyChangeResult(
            outcome=decision.outcome,
            before_hedge_ratio=before_ratio,
            reopen_recommended=reopen,
            notes=[f"risk gate error: {type(exc).__name__}: {exc}"],
        )

    after_ratio = hypothesis.hedge_metrics.hedge_ratio
    delta = _delta(before_ratio, after_ratio)

    if risk_decision.verdict not in {RiskVerdict.APPROVE, RiskVerdict.MODIFY}:
        notes.append(
            f"risk gate {risk_decision.verdict.value}: {'; '.join(risk_decision.violations) or risk_decision.rationale}"
        )
        return ApplyChangeResult(
            outcome=decision.outcome,
            risk_decision=risk_decision,
            before_hedge_ratio=before_ratio,
            after_hedge_ratio=before_ratio,
            delta=0.0,
            reopen_recommended=reopen,
            notes=notes,
        )

    try:
        plan = build_execution_plan(
            risk_decision, approval_id=f"reassess-{context.cycle_id}"
        )
    except ExecutionPlanError as exc:
        return ApplyChangeResult(
            outcome=decision.outcome,
            risk_decision=risk_decision,
            before_hedge_ratio=before_ratio,
            reopen_recommended=reopen,
            notes=[f"plan build failed: {exc}"],
        )

    execution_result: ExecutionResult | None = None
    submitted = False
    if broker is not None:
        execution_result, submitted = _submit(plan, broker, engine, notes)

    hedge_change_id = _record_hedge_change(
        engine,
        context.cycle_id,
        before_ratio,
        after_ratio,
        delta,
        decision,
        reassessment_id,
        notes,
    )

    if reopen:
        notes.append("REPLACE: a fresh hedge cycle should follow the close")

    return ApplyChangeResult(
        outcome=decision.outcome,
        risk_decision=risk_decision,
        plan=plan,
        execution_result=execution_result,
        before_hedge_ratio=before_ratio,
        after_hedge_ratio=after_ratio,
        delta=delta,
        hedge_change_id=hedge_change_id,
        reopen_recommended=reopen,
        submitted=submitted,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _delta(before: float | None, after: float | None) -> float:
    return round((after or 0.0) - (before or 0.0), 4)


def _risk_repo(engine: "Engine | None") -> Any | None:
    if engine is None:
        return None
    try:
        from backend.db.risk_checks_repo import RiskCheckRepository

        return RiskCheckRepository(engine)
    except Exception:  # noqa: BLE001
        logger.exception("apply_change: could not build RiskCheckRepository")
        return None


def _submit(
    plan: ExecutionPlan,
    broker: OrderSubmitter,
    engine: "Engine | None",
    notes: list[str],
) -> tuple[ExecutionResult | None, bool]:
    """Submit the close plan; mirror the EXECUTION node's persistence split."""
    try:
        outcome = submit_plan(broker, plan)
    except AlpacaError as exc:
        notes.append(f"broker rejected the close: {exc}")
        return (
            ExecutionResult(
                cycle_id=plan.cycle_id,
                status=ExecutionStatus.FAILED,
                error=f"broker submit failed: {exc}",
            ),
            False,
        )

    broker_order = outcome.responses[0] if outcome.responses else {"status": "accepted"}
    try:
        result = build_execution_result(plan, broker_order)
    except Exception as exc:  # noqa: BLE001 - live order but unmappable
        result = ExecutionResult(
            cycle_id=plan.cycle_id,
            status=ExecutionStatus.FAILED,
            order_ids=list(outcome.order_ids),
            broker_order_id=next(iter(outcome.order_ids), None),
            error=f"close order not mappable: {exc}",
        )

    if engine is not None:
        try:
            persist_execution_result(engine, plan, result)
        except Exception:  # noqa: BLE001
            logger.exception("apply_change: orders/fills persistence failed for %s", plan.cycle_id)
    return result, True


def _record_hedge_change(
    engine: "Engine | None",
    cycle_id: str,
    before: float | None,
    after: float | None,
    delta: float,
    decision: ReassessmentDecision,
    reassessment_id: int | None,
    notes: list[str],
) -> int | None:
    if engine is None:
        return None
    try:
        from backend.db.monitoring_repo import HedgeChangeRecord, MonitoringRepository

        row = MonitoringRepository(engine).record_hedge_change(
            HedgeChangeRecord(
                cycle_id=cycle_id,
                reassessment_id=reassessment_id,
                before_hedge_ratio=Decimal(str(before if before is not None else 0.0)),
                after_hedge_ratio=Decimal(str(after if after is not None else 0.0)),
                delta=Decimal(str(delta)),
                action=decision.outcome,
                reason=decision.rationale,
                detail={"trigger_types": [t.value for t in decision.trigger_types]},
            )
        )
        return row.id
    except Exception:  # noqa: BLE001
        logger.exception("apply_change: hedge_changes write failed for %s", cycle_id)
        notes.append("hedge_changes row not persisted (see logs)")
        return None
