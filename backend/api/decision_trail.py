"""Decision-trail endpoint — task P8-BE-4.

``GET /decision-trail/{order_id}`` reconstructs, for one submitted trade, the full
chain of reasoning that produced it:

    order → risk approval → strategy decision → hypotheses → analysis context → trigger

Every hop is keyed by the order's ``cycle_id``. A hop with no persisted row is
returned as ``null`` (or ``[]`` for the hypotheses list) **and** named in
``missing_links`` — a broken chain is reported, never silently dropped. The
endpoint 404s only when the anchor order itself does not exist; any other gap
still returns ``200`` with the partial trail and ``complete: false``.

Reads go through the same synchronous repositories and engine the other read-back
endpoints use — :func:`backend.api.readback.get_readback_engine`, a FastAPI
dependency the test suite overrides to point at a scratch database.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.monitoring_repo import MonitoringRepository
from backend.db.orders_repo import OrderRepository
from backend.db.repository import PortfolioSnapshotRepository
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.db.strategy_repo import (
    StrategyDecisionRepository,
    StrategyHypothesisRepository,
)

router = APIRouter(tags=["decision-trail"])


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


class FillNode(BaseModel):
    id: int
    leg_symbol: str
    qty: float
    price: float
    slippage: float | None = None


class OrderNode(BaseModel):
    id: int
    cycle_id: str
    order_class: str
    status: str
    legs: list[Any] | None = None
    broker_order_id: str | None = None
    submitted_at: _dt.datetime
    fills: list[FillNode]


class RiskApprovalNode(BaseModel):
    id: int
    cycle_id: str
    verdict: str
    checks: list[Any] | None = None
    violations: list[Any] | None = None
    warnings: list[Any] | None = None
    modifications: list[Any] | None = None


class StrategyDecisionNode(BaseModel):
    id: int
    cycle_id: str
    action: str
    rationale: str
    selected_hypothesis_id: int | None = None
    alternatives: list[Any] | dict[str, Any] | None = None
    comparison: list[Any] | dict[str, Any] | None = None


class HypothesisNode(BaseModel):
    id: int
    cycle_id: str
    strategy_type: str
    verdict: str
    legs: list[Any] | None = None
    metrics: dict[str, Any] | None = None
    rejection_reason: str | None = None
    selected: bool


class PositionNode(BaseModel):
    symbol: str
    qty: float
    avg_price: float
    market_value: float
    asset_class: str
    side: str


class AnalysisContextNode(BaseModel):
    snapshot_id: int
    cycle_id: str
    ts: _dt.datetime
    total_value: float
    cash: float
    equity: float
    buying_power: float
    volatility: float | None = None
    beta: float | None = None
    drawdown: float | None = None
    positions: list[PositionNode]


class MonitoringEventNode(BaseModel):
    id: int
    cycle_id: str
    trigger_type: str
    observed: dict[str, Any] | None = None
    threshold: float | None = None
    fired_at: _dt.datetime | None = None


class ReassessmentNode(BaseModel):
    id: int
    cycle_id: str
    trigger_event_id: int | None = None
    outcome: str
    reason: str
    context: dict[str, Any] | None = None
    created_at: _dt.datetime | None = None


class TriggerNode(BaseModel):
    monitoring_events: list[MonitoringEventNode]
    reassessments: list[ReassessmentNode]


class DecisionTrailOut(BaseModel):
    order_id: int
    cycle_id: str
    order: OrderNode
    risk_approval: RiskApprovalNode | None = None
    strategy_decision: StrategyDecisionNode | None = None
    hypotheses: list[HypothesisNode]
    analysis_context: AnalysisContextNode | None = None
    trigger: TriggerNode | None = None
    missing_links: list[str]
    complete: bool


@router.get("/decision-trail/{order_id}", response_model=DecisionTrailOut)
def decision_trail(
    order_id: int,
    engine: Engine = Depends(get_readback_engine),
) -> DecisionTrailOut:
    """Return the full linked reasoning chain behind ``order_id``.

    404 only when the order does not exist; a downstream gap is reported in
    ``missing_links`` with ``complete: false``, never omitted.
    """
    orders = OrderRepository(engine)
    anchor = orders.get(order_id)
    if anchor is None or anchor.id is None:
        raise HTTPException(status_code=404, detail=f"no order with id {order_id}")

    cycle_id = anchor.cycle_id
    missing: list[str] = []

    order_node = OrderNode(
        id=anchor.id,
        cycle_id=anchor.cycle_id,
        order_class=anchor.order_class,
        status=anchor.status,
        legs=anchor.legs,
        broker_order_id=anchor.broker_order_id,
        submitted_at=anchor.submitted_at,
        fills=[
            FillNode(
                id=fill.id,  # type: ignore[arg-type]  # persisted rows carry an id
                leg_symbol=fill.leg_symbol,
                qty=float(fill.qty),
                price=float(fill.price),
                slippage=_f(fill.slippage),
            )
            for fill in orders.fills_for(anchor.id)
        ],
    )

    # -- risk approval -------------------------------------------------------- #
    risk = RiskCheckRepository(engine).for_cycle(cycle_id)
    risk_node = (
        None
        if risk is None or risk.id is None
        else RiskApprovalNode(
            id=risk.id,
            cycle_id=risk.cycle_id,
            verdict=risk.verdict,
            checks=risk.checks,
            violations=risk.violations,
            warnings=risk.warnings,
            modifications=risk.modifications,
        )
    )
    if risk_node is None:
        missing.append("risk_approval")

    # -- strategy decision ------------------------------------------------- #
    decision = StrategyDecisionRepository(engine).for_cycle(cycle_id)
    decision_node = (
        None
        if decision is None or decision.id is None
        else StrategyDecisionNode(
            id=decision.id,
            cycle_id=decision.cycle_id,
            action=decision.action,
            rationale=decision.rationale,
            selected_hypothesis_id=decision.selected_hypothesis_id,
            alternatives=decision.alternatives,
            comparison=decision.comparison,
        )
    )
    if decision_node is None:
        missing.append("strategy_decision")

    # -- hypotheses ------------------------------------------------------- #
    selected_id = decision.selected_hypothesis_id if decision is not None else None
    hypotheses = StrategyHypothesisRepository(engine).list_for_cycle(cycle_id)
    hypothesis_nodes = [
        HypothesisNode(
            id=h.id,  # type: ignore[arg-type]
            cycle_id=h.cycle_id,
            strategy_type=h.strategy_type,
            verdict=h.verdict,
            legs=h.legs,
            metrics=h.metrics,
            rejection_reason=h.rejection_reason,
            selected=h.id is not None and h.id == selected_id,
        )
        for h in hypotheses
    ]
    if not hypothesis_nodes:
        missing.append("hypotheses")

    # -- analysis context ----------------------------------------------- #
    snapshots = PortfolioSnapshotRepository(engine)
    snapshot = snapshots.for_cycle(cycle_id)
    context_node = None
    if snapshot is not None and snapshot.id is not None:
        context_node = AnalysisContextNode(
            snapshot_id=snapshot.id,
            cycle_id=snapshot.cycle_id,
            ts=snapshot.ts,
            total_value=float(snapshot.total_value),
            cash=float(snapshot.cash),
            equity=float(snapshot.equity),
            buying_power=float(snapshot.buying_power),
            volatility=_f(snapshot.volatility),
            beta=_f(snapshot.beta),
            drawdown=_f(snapshot.drawdown),
            positions=[
                PositionNode(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_price=float(p.avg_price),
                    market_value=float(p.market_value),
                    asset_class=p.asset_class,
                    side=p.side,
                )
                for p in snapshots.positions_for(snapshot.id)
            ],
        )
    if context_node is None:
        missing.append("analysis_context")

    # -- trigger ------------------------------------------------------- #
    monitoring = MonitoringRepository(engine)
    events = monitoring.list_events(cycle_id)
    reassessments = monitoring.list_reassessments(cycle_id)
    trigger_node: TriggerNode | None = None
    if events or reassessments:
        trigger_node = TriggerNode(
            monitoring_events=[
                MonitoringEventNode(
                    id=e.id,  # type: ignore[arg-type]
                    cycle_id=e.cycle_id,
                    trigger_type=str(e.trigger_type),
                    observed=e.observed,
                    threshold=_f(e.threshold),
                    fired_at=e.fired_at,
                )
                for e in events
            ],
            reassessments=[
                ReassessmentNode(
                    id=r.id,  # type: ignore[arg-type]
                    cycle_id=r.cycle_id,
                    trigger_event_id=r.trigger_event_id,
                    outcome=str(r.outcome),
                    reason=r.reason,
                    context=r.context,
                    created_at=r.created_at,
                )
                for r in reassessments
            ],
        )
    if trigger_node is None:
        missing.append("trigger")

    return DecisionTrailOut(
        order_id=anchor.id,
        cycle_id=cycle_id,
        order=order_node,
        risk_approval=risk_node,
        strategy_decision=decision_node,
        hypotheses=hypothesis_nodes,
        analysis_context=context_node,
        trigger=trigger_node,
        missing_links=missing,
        complete=not missing,
    )
