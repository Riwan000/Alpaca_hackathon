"""``POST /execute`` — task **P5-BE-15** (BRD §21–23).

One call = one execution cycle for an already-approved decision:

1. Accept an approved :class:`~backend.models.risk.RiskDecision` plus a fresh
   :class:`~backend.models.hedge_context.HedgeContext` (JSON body).
2. Persist the risk evaluation as a ``risk_checks`` row.
3. Build the :class:`~backend.models.execution.ExecutionPlan` from the approved
   (possibly ``MODIFY``-adjusted) hypothesis — P5-BE-10.
4. Run pre-flight validation against the fresh context; on drift, log an
   ``execution_failures`` row and return a ``FAILED`` result **without sending
   an order** — P5-BE-11.
5. Submit one multi-leg combo order via Alpaca, legging in only if combos are
   unsupported — P5-BE-12.
6. Map the broker order to an :class:`~backend.models.execution.ExecutionResult`
   (``FILLED`` / ``PARTIALLY_FILLED`` / ``FAILED`` / ``CANCELLED``) and persist
   the ``orders`` row + one ``fills`` row per filled leg — P5-BE-13/14.
7. Return the :class:`ExecutionResult` (200).

The DB engine is the shared read-back engine
(:func:`backend.api.readback.get_readback_engine`) so ``GET /orders`` and
``GET /risk/checks`` see this cycle immediately. The broker is injectable via a
FastAPI dependency so the test suite swaps a fake for the live Alpaca client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from backend.agents.execution import (
    ExecutionPlanError,
    ExecutionResultError,
    build_execution_plan,
    build_execution_result,
    persist_execution_result,
    run_preflight,
)
from backend.api.readback import get_readback_engine
from backend.db.execution_failures_repo import (
    ExecutionFailureRecord,
    ExecutionFailureRepository,
)
from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository
from backend.integrations.alpaca.client import AlpacaError
from backend.integrations.alpaca.orders import OrderSubmitter, SubmitOutcome, submit_plan
from backend.models.enums import ExecutionStatus, RiskVerdict
from backend.models.execution import ExecutionPlan, ExecutionResult
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskDecision

logger = logging.getLogger(__name__)

router = APIRouter(tags=["execution"])

_APPROVED_VERDICTS = {RiskVerdict.APPROVE, RiskVerdict.MODIFY}


class ExecuteRequest(BaseModel):
    """Body for ``POST /execute``: an approved decision + a fresh context."""

    decision: RiskDecision
    context: HedgeContext
    approval_id: str | None = Field(
        default=None,
        description="id of the risk evaluation clearing this plan; defaults to risk-<cycle>",
    )
    preflight: bool = Field(
        default=True, description="re-validate the plan against the fresh context before submit"
    )


def get_execution_broker() -> OrderSubmitter | None:
    """Return ``None`` — the endpoint builds a live Alpaca client itself.

    Tests override this to inject a fake broker with a ``submit_order`` method.
    """
    return None


def _live_broker() -> OrderSubmitter:
    from backend.integrations.alpaca.client import AlpacaClient

    return AlpacaClient()


def _persist_failure(
    engine: Engine, cycle_id: str, stage: str, reason: str, code: str | None = None
) -> None:
    try:
        ExecutionFailureRepository(engine).create(
            ExecutionFailureRecord(
                cycle_id=cycle_id,
                stage=stage,
                reason=reason,
                detail={"code": code} if code else None,
            )
        )
    except Exception:  # noqa: BLE001 - an audit-row write must never mask the real result
        logger.exception("execute: failed to write execution_failures row for %s", cycle_id)


def _persist_risk_check(engine: Engine, decision: RiskDecision) -> None:
    RiskCheckRepository(engine).create(
        RiskCheckRecord(
            cycle_id=decision.cycle_id,
            verdict=decision.verdict.value,
            checks=[c.model_dump(mode="json") for c in decision.checks] or None,
            violations=list(decision.violations) or None,
            warnings=list(decision.warnings) or None,
            modifications=[m.model_dump(mode="json") for m in decision.modifications]
            or None,
        )
    )


def _combine_legged(outcome: SubmitOutcome) -> dict[str, Any]:
    """Fold independent single-leg responses into one combo-shaped order object."""
    legs = list(outcome.responses)
    order_ids = outcome.order_ids
    statuses = {str(leg.get("status") or "").strip().lower() for leg in legs}
    if statuses == {"filled"}:
        parent_status = "filled"
    elif statuses & {"filled", "partially_filled"}:
        parent_status = "partially_filled"
    elif statuses & {"rejected"}:
        parent_status = "rejected"
    else:
        parent_status = next(iter(statuses), "") or "canceled"
    return {
        "id": order_ids[0] if order_ids else None,
        "status": parent_status,
        "legs": legs,
    }


@router.post("/execute", response_model=ExecutionResult)
def execute(
    request: ExecuteRequest,
    engine: Engine = Depends(get_readback_engine),
    broker: OrderSubmitter | None = Depends(get_execution_broker),
) -> ExecutionResult:
    """Execute an approved decision: plan → pre-flight → order → result.

    Returns:
        The :class:`ExecutionResult` (200), including a truthful ``FAILED`` on a
        pre-flight abort or a broker rejection.

    Raises:
        HTTPException 422: the decision is not ``APPROVE`` / ``MODIFY``, carries
            no approved hypothesis, or cannot be turned into a plan.
        HTTPException 500: execution ran but persisting its result failed.
    """
    decision = request.decision
    if decision.verdict not in _APPROVED_VERDICTS or decision.approved_hypothesis is None:
        raise HTTPException(
            status_code=422,
            detail="execute requires an APPROVE/MODIFY decision with an approved hypothesis",
        )

    approval_id = request.approval_id or f"risk-{decision.cycle_id}"

    try:
        _persist_risk_check(engine, decision)
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute: risk-check persistence failed for %s", decision.cycle_id)
        raise HTTPException(
            status_code=500, detail=f"could not persist the risk evaluation: {exc}"
        ) from exc

    try:
        plan: ExecutionPlan = build_execution_plan(decision, approval_id=approval_id)
    except ExecutionPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ---- pre-flight (P5-BE-11) — abort before any order is sent -------------
    if request.preflight:
        pf = run_preflight(plan, request.context)
        if not pf.ok:
            _persist_failure(engine, plan.cycle_id, "PREFLIGHT", pf.reason, pf.code)
            return ExecutionResult(
                cycle_id=plan.cycle_id,
                status=ExecutionStatus.FAILED,
                error=f"pre-flight abort [{pf.code}]: {pf.reason}",
            )

    # ---- submit (P5-BE-12) ------------------------------------------------
    submitter = broker or _live_broker()
    try:
        outcome = submit_plan(submitter, plan)
    except AlpacaError as exc:
        _persist_failure(engine, plan.cycle_id, "SUBMIT", str(exc))
        return ExecutionResult(
            cycle_id=plan.cycle_id,
            status=ExecutionStatus.FAILED,
            error=f"broker submit failed: {exc}",
        )

    broker_order = outcome.responses[0] if outcome.combo else _combine_legged(outcome)

    # ---- map + persist (P5-BE-13/14) ------------------------------------
    try:
        result = build_execution_result(plan, broker_order)
    except ExecutionResultError as exc:
        _persist_failure(engine, plan.cycle_id, "RESULT", str(exc))
        return ExecutionResult(
            cycle_id=plan.cycle_id,
            status=ExecutionStatus.FAILED,
            error=f"broker order not terminal: {exc}",
        )

    try:
        persist_execution_result(engine, plan, result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute: result persistence failed for %s", plan.cycle_id)
        raise HTTPException(
            status_code=500,
            detail=f"execution completed but persisting orders/fills failed: {exc}",
        ) from exc

    return result
