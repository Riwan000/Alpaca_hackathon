"""Execution read-back endpoints — task P5-DB-4.

Two GETs that let the dashboard (and ``curl``) read what the risk gate and
execution steps wrote:

* ``GET /risk/checks?cycle_id=`` — the ``risk_checks`` rows for that cycle
  (verdict + the deterministic checklist + violations / warnings /
  modifications); without ``cycle_id``, every row. Backs the ``RiskChecklist``
  panel (P5-FE-2 / P5-FE-4).
* ``GET /orders?cycle_id=`` — the ``orders`` for that cycle, **each with its
  ``fills`` nested**; without ``cycle_id``, every order. Backs the
  ``OrderStatus`` indicator (P5-FE-3).

Both read through the synchronous repositories
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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.orders_repo import OrderRepository
from backend.db.risk_checks_repo import RiskCheckRepository

router = APIRouter(tags=["exec-readback"])


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
