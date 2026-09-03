"""Monitoring read-back endpoints — task P7-DB-5.

Exposes:
- `GET /monitoring/state` — latest current vs target hedge, cooldown timestamp, and active status
- `GET /monitoring/events` — level 1 trigger events optionally filtered by cycle_id
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.monitoring_repo import MonitoringRepository

router = APIRouter(tags=["monitoring"])


class MonitoringStateOut(BaseModel):
    id: int | None = None
    cycle_id: str | None = None
    current_hedge: float
    target_hedge: float
    cooldown_until: _dt.datetime | None = None
    trigger_history: list[Any] = []
    monitoring_status: str = "ACTIVE"
    detail: dict[str, Any] | None = None
    updated_at: _dt.datetime | None = None


class MonitoringEventOut(BaseModel):
    id: int
    cycle_id: str
    trigger_type: str
    observed: dict[str, Any] | None = None
    threshold: float | None = None
    fired_at: _dt.datetime


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


@router.get("/monitoring/state", response_model=MonitoringStateOut)
def get_monitoring_state(
    engine: Engine = Depends(get_readback_engine),
) -> MonitoringStateOut:
    """Return latest monitoring state including hedge ratios and cooldown."""
    repo = MonitoringRepository(engine)
    state = repo.get_latest_state()
    if not state:
        return MonitoringStateOut(
            current_hedge=0.0,
            target_hedge=0.0,
            cooldown_until=None,
            trigger_history=[],
            monitoring_status="IDLE",
            updated_at=_dt.datetime.now(_dt.timezone.utc),
        )

    return MonitoringStateOut(
        id=state.id,
        cycle_id=state.cycle_id,
        current_hedge=float(state.current_hedge),
        target_hedge=float(state.target_hedge),
        cooldown_until=state.cooldown_until,
        trigger_history=state.trigger_history,
        monitoring_status=state.monitoring_status,
        detail=state.detail,
        updated_at=state.updated_at,
    )


@router.get("/monitoring/events", response_model=list[MonitoringEventOut])
def list_monitoring_events(
    cycle_id: str | None = Query(
        default=None, description="Optional cycle_id filter"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> list[MonitoringEventOut]:
    """Return monitoring trigger events ordered by fired_at ascending."""
    repo = MonitoringRepository(engine)
    events = repo.list_events(cycle_id=cycle_id)
    return [
        MonitoringEventOut(
            id=e.id,  # type: ignore[arg-type]
            cycle_id=e.cycle_id,
            trigger_type=str(e.trigger_type),
            observed=e.observed,
            threshold=_f(e.threshold),
            fired_at=e.fired_at,  # type: ignore[arg-type]
        )
        for e in events
    ]
