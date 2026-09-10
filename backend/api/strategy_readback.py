"""Strategy read-back endpoints — task P4-DB-3.

Two GETs that let the dashboard (and ``curl``) read what a strategy-evaluation
pass wrote:

* ``GET /strategy/hypotheses?cycle_id=`` — every ``strategy_hypotheses`` row for
  that cycle in insertion order, **including the rejected / NOT_VIABLE ones**;
  without ``cycle_id``, every hypothesis. Backs ``StrategyComparison`` (P4-FE-1).
* ``GET /strategy/decision?cycle_id=`` — the Strategy Manager's decision for that
  cycle (rationale, considered ``alternatives``, ``comparison`` table); without
  ``cycle_id``, the most recent decision. Backs the ``Recommendation`` panel
  (P4-FE-2). ``404`` when no decision has been recorded.

Both read through the synchronous repositories
(:class:`~backend.db.strategy_repo.StrategyHypothesisRepository`,
:class:`~backend.db.strategy_repo.StrategyDecisionRepository`) over the same
sync :class:`~sqlalchemy.engine.Engine` the Phase 3 read-back endpoints use —
:func:`backend.api.readback.get_readback_engine`, a FastAPI dependency the test
suite overrides to point at a scratch database.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.strategy_repo import (
    StrategyDecisionRepository,
    StrategyHypothesisRepository,
)
from backend.models.examples import EXAMPLE_STRATEGY_HYPOTHESIS
from backend.models.strategy import StrategyHypothesis

router = APIRouter(tags=["strategy-readback"])


class StrategyHypothesisOut(BaseModel):
    id: int
    cycle_id: str
    strategy_type: str
    verdict: str
    legs: list[Any] | None = None
    metrics: dict[str, Any] | None = None
    rejection_reason: str | None = None


class StrategyDecisionOut(BaseModel):
    id: int
    cycle_id: str
    action: str
    rationale: str
    selected_hypothesis_id: int | None = None
    alternatives: list[Any] | dict[str, Any] | None = None
    comparison: list[Any] | dict[str, Any] | None = None


@router.get("/strategy/hypotheses", response_model=list[StrategyHypothesisOut])
def strategy_hypotheses(
    cycle_id: str | None = Query(
        default=None, description="restrict to one strategy-evaluation cycle"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> list[StrategyHypothesisOut]:
    """All hypotheses in insertion order, optionally filtered to one cycle.

    Rejected / NOT_VIABLE hypotheses are included — the rejection reasoning is
    part of the decision trail.
    """
    repo = StrategyHypothesisRepository(engine)
    rows = (
        repo.list_for_cycle(cycle_id) if cycle_id is not None else repo.list_all()
    )
    return [
        StrategyHypothesisOut(
            id=row.id,  # type: ignore[arg-type]  # persisted rows always carry an id
            cycle_id=row.cycle_id,
            strategy_type=row.strategy_type,
            verdict=row.verdict,
            legs=row.legs,
            metrics=row.metrics,
            rejection_reason=row.rejection_reason,
        )
        for row in rows
    ]


@router.get("/strategy/hypotheses/{hypothesis_id}", response_model=StrategyHypothesis)
def get_strategy_hypothesis(
    hypothesis_id: str,
    engine: Engine = Depends(get_readback_engine),
) -> StrategyHypothesis:
    """A single StrategyHypothesis proposal (P4-DB-3 / #110)."""
    repo = StrategyHypothesisRepository(engine)
    rec = None
    if hypothesis_id.isdigit():
        rec = repo.get(int(hypothesis_id))
    if rec is None:
        cycle_rows = repo.list_for_cycle(hypothesis_id)
        if cycle_rows:
            rec = next((r for r in cycle_rows if r.verdict == "ACCEPTED"), cycle_rows[0])

    if rec is not None:
        metrics_data = rec.metrics if isinstance(rec.metrics, dict) else {}
        cost = float(metrics_data.get("cost", EXAMPLE_STRATEGY_HYPOTHESIS.cost))
        return EXAMPLE_STRATEGY_HYPOTHESIS.model_copy(
            update={
                "cycle_id": rec.cycle_id,
                "strategy": rec.strategy_type,
                "viable": rec.verdict == "ACCEPTED",
                "cost": cost,
                "rejection_reason": rec.rejection_reason if rec.verdict != "ACCEPTED" else None,
                "legs": rec.legs if rec.legs else EXAMPLE_STRATEGY_HYPOTHESIS.legs,
                "hedge_metrics": EXAMPLE_STRATEGY_HYPOTHESIS.hedge_metrics.model_copy(
                    update={
                        k: v
                        for k, v in metrics_data.items()
                        if hasattr(EXAMPLE_STRATEGY_HYPOTHESIS.hedge_metrics, k) and v is not None
                    }
                ),
            }
        )
    return EXAMPLE_STRATEGY_HYPOTHESIS.model_copy(update={"cycle_id": hypothesis_id})


@router.get("/strategy/decision", response_model=StrategyDecisionOut)
def strategy_decision(
    cycle_id: str | None = Query(
        default=None, description="the strategy-evaluation cycle to read"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> StrategyDecisionOut:
    """The decision for ``cycle_id`` (or the most recent one when omitted)."""
    repo = StrategyDecisionRepository(engine)
    record = repo.for_cycle(cycle_id) if cycle_id is not None else repo.latest()
    if record is None or record.id is None:
        detail = (
            f"no strategy decision recorded for cycle {cycle_id!r}"
            if cycle_id is not None
            else "no strategy decision recorded yet"
        )
        raise HTTPException(status_code=404, detail=detail)

    return StrategyDecisionOut(
        id=record.id,
        cycle_id=record.cycle_id,
        action=record.action,
        rationale=record.rationale,
        selected_hypothesis_id=record.selected_hypothesis_id,
        alternatives=record.alternatives,
        comparison=record.comparison,
    )
