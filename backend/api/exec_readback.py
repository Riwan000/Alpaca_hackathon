"""Execution read-back endpoints — task P5-DB-4.

Three GETs that let the dashboard (and ``curl``) read what the risk gate and
execution steps wrote:

* ``GET /risk/checks?cycle_id=`` — the ``risk_checks`` rows for that cycle
  (verdict + the deterministic checklist + violations / warnings /
  modifications); without ``cycle_id``, every row. Backs the ``RiskChecklist``
  panel (P5-FE-2 / P5-FE-4).
* ``GET /orders?cycle_id=`` — the ``orders`` for that cycle, **each with its
  ``fills`` nested**; without ``cycle_id``, every order. Backs the
  ``OrderStatus`` indicator (P5-FE-3).
* ``GET /execution?cycle_id=`` — the most recently persisted order for that
  cycle, reshaped into an :class:`~backend.models.execution.ExecutionResult`
  (the same contract ``POST /execute`` returns live); without ``cycle_id``,
  the most recently submitted order across all cycles. Replaces the
  hardcoded fixture that used to live at this path in ``backend/api/stubs.py``
  — a ``NO_HEDGE`` decision never reaches ``/execute``, so "no order for this
  cycle" is a legitimate 404, not an error.

All three read through the synchronous repositories
(:class:`~backend.db.risk_checks_repo.RiskCheckRepository`,
:class:`~backend.db.orders_repo.OrderRepository`) over the same sync
:class:`~sqlalchemy.engine.Engine` the Phase 3 / 4 read-back endpoints use —
:func:`backend.api.readback.get_readback_engine`, a FastAPI dependency the test
suite overrides to point at a scratch database.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.orders_repo import OrderRecord, OrderRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.models.enums import ExecutionStatus
from backend.models.execution import ExecutionResult, FailedLeg, FilledLeg
from backend.quant.payoff import OPTION_MULTIPLIER

router = APIRouter(tags=["exec-readback"])

#: ``orders.status`` (persisted lifecycle) → the terminal contract enum a
#: read-back caller expects — the inverse of
#: ``backend.agents.execution.result._EXECUTION_TO_ORDER_STATUS``.
_ORDER_STATUS_TO_EXECUTION: dict[str, ExecutionStatus] = {
    "FILLED": ExecutionStatus.FILLED,
    "PARTIALLY_FILLED": ExecutionStatus.PARTIALLY_FILLED,
    "CANCELLED": ExecutionStatus.CANCELLED,
    "EXPIRED": ExecutionStatus.CANCELLED,
    "REJECTED": ExecutionStatus.FAILED,
}
#: Anything not a key above (PENDING, SUBMITTED) is a non-terminal lifecycle
#: state — deliberately absent, so the endpoint 404s instead of fabricating a
#: terminal result for an order that hasn't finished yet.


class RiskCheckOut(BaseModel):
    id: int
    cycle_id: str
    verdict: str
    checks: list[Any] | None = None
    violations: list[Any] | None = None
    warnings: list[Any] | None = None
    modifications: list[Any] | None = None


class FillOut(BaseModel):
    id: int
    order_id: int
    leg_symbol: str
    qty: float
    price: float
    slippage: float | None = None
    filled_at: _dt.datetime


class OrderOut(BaseModel):
    id: int
    cycle_id: str
    order_class: str
    status: str
    legs: list[Any] | None = None
    broker_order_id: str | None = None
    submitted_at: _dt.datetime
    fills: list[FillOut]


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


@router.get("/risk/checks", response_model=list[RiskCheckOut])
def risk_checks(
    cycle_id: str | None = Query(
        default=None, description="restrict to one risk-evaluation cycle"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> list[RiskCheckOut]:
    """Risk checks in insertion order, optionally filtered to one cycle."""
    repo = RiskCheckRepository(engine)
    rows = repo.list_for_cycle(cycle_id) if cycle_id is not None else repo.list_all()
    return [
        RiskCheckOut(
            id=row.id,  # type: ignore[arg-type]  # persisted rows always carry an id
            cycle_id=row.cycle_id,
            verdict=row.verdict,
            checks=row.checks,
            violations=row.violations,
            warnings=row.warnings,
            modifications=row.modifications,
        )
        for row in rows
    ]


@router.get("/orders", response_model=list[OrderOut])
def orders(
    cycle_id: str | None = Query(
        default=None, description="restrict to one execution cycle"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> list[OrderOut]:
    """Orders in insertion order with their fills nested, optionally by cycle."""
    repo = OrderRepository(engine)
    rows = repo.list_for_cycle(cycle_id) if cycle_id is not None else repo.list_all()
    return [
        OrderOut(
            id=order.id,  # type: ignore[arg-type]  # persisted rows always carry an id
            cycle_id=order.cycle_id,
            order_class=order.order_class,
            status=order.status,
            legs=order.legs,
            broker_order_id=order.broker_order_id,
            submitted_at=order.submitted_at,
            fills=[
                FillOut(
                    id=fill.id,  # type: ignore[arg-type]
                    order_id=fill.order_id,
                    leg_symbol=fill.leg_symbol,
                    qty=float(fill.qty),
                    price=float(fill.price),
                    slippage=_f(fill.slippage),
                    filled_at=fill.filled_at,
                )
                for fill in repo.fills_for(order.id)  # type: ignore[arg-type]
            ],
        )
        for order in rows
    ]


def _latest(rows: list[OrderRecord]) -> OrderRecord | None:
    """The most recently inserted row, or ``None`` — ``rows`` is id-ascending."""
    return rows[-1] if rows else None


@router.get("/execution", response_model=ExecutionResult)
def execution_result(
    cycle_id: str | None = Query(default=None, description="Cycle to inspect; omit for latest"),
    engine: Engine = Depends(get_readback_engine),
) -> ExecutionResult:
    """The most recently persisted order for a cycle, as an ExecutionResult.

    cycle_id is optional; omitting it returns the most recently submitted
    order across all cycles (mirrors ``GET /workflow-state``'s "omit for
    latest" convention). Raises 404 when no order has been persisted for that
    cycle — a NO_HEDGE decision never reaches ``POST /execute``, so having no
    order to report is a legitimate outcome, not a server error.
    """
    repo = OrderRepository(engine)
    order = _latest(repo.list_for_cycle(cycle_id) if cycle_id is not None else repo.list_all())
    if order is None or order.id is None:
        raise HTTPException(status_code=404, detail="No execution found for this cycle")

    status = _ORDER_STATUS_TO_EXECUTION.get(order.status)
    if status is None:
        # order.status is a non-terminal lifecycle state (PENDING/SUBMITTED) —
        # there is no truthful terminal ExecutionResult to report yet, mirrors
        # backend.agents.execution.result.map_broker_status's refusal to
        # report a still-working broker order as done.
        raise HTTPException(
            status_code=404,
            detail=f"order for this cycle has not reached a terminal state yet ({order.status})",
        )

    fills = repo.fills_for(order.id)
    # qty is a DB Numeric; round rather than truncate (mirrors the live
    # int(round(filled_qty)) in build_execution_result) and drop anything
    # that still can't satisfy FilledLeg's qty > 0 rather than raising.
    filled_legs = [
        leg
        for leg in (
            FilledLeg(
                leg_symbol=fill.leg_symbol,
                qty=int(round(float(fill.qty))),
                price=float(fill.price),
                filled_at=fill.filled_at,
                slippage=_f(fill.slippage),
            )
            if int(round(float(fill.qty))) > 0
            else None
            for fill in fills
        )
        if leg is not None
    ]

    # failed_legs is only meaningful (and only required by the contract) for
    # PARTIALLY_FILLED — FILLED/CANCELLED/FAILED all forbid or don't need it,
    # and orders.status is the authoritative terminal state regardless of
    # whether the persisted occ_symbol casing happens to line up with the
    # fills' leg_symbol.
    failed_legs: list[FailedLeg] = []
    if status is ExecutionStatus.PARTIALLY_FILLED:
        filled_symbols = {fill.leg_symbol.strip().upper() for fill in fills}
        planned_symbols = {
            str(leg["occ_symbol"]).strip().upper()
            for leg in (order.legs or [])
            if isinstance(leg, dict) and leg.get("occ_symbol")
        }
        failed_legs = [
            FailedLeg(leg_symbol=symbol, reason="not filled")
            for symbol in sorted(planned_symbols - filled_symbols)
        ]
        # The contract requires at least one failed leg here; fall back to a
        # generic entry when the plan's occ symbols weren't persisted on the
        # order row (or didn't line up) so the shape stays honest either way.
        if not failed_legs:
            failed_legs = [
                FailedLeg(leg_symbol="unknown", reason="unfilled leg detail not persisted")
            ]

    slippages = [_f(fill.slippage) for fill in fills if fill.slippage is not None]
    error = None
    if status is ExecutionStatus.FAILED:
        error = "broker order rejected (no fill detail persisted)"

    return ExecutionResult(
        cycle_id=order.cycle_id,
        status=status,
        order_ids=[order.broker_order_id] if order.broker_order_id else [],
        broker_order_id=order.broker_order_id,
        filled_legs=filled_legs,
        failed_legs=failed_legs,
        actual_cost=(
            round(sum(leg.price * leg.qty * OPTION_MULTIPLIER for leg in filled_legs), 4)
            if filled_legs
            else None
        ),
        slippage=round(sum(s for s in slippages if s is not None) / len(slippages), 6)
        if slippages
        else None,
        submitted_at=order.submitted_at,
        completed_at=fills[-1].filled_at if fills else order.submitted_at,
        error=error,
        recovery_action=None,
    )
