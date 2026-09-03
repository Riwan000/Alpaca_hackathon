"""P&L and Performance read-back endpoints — task P8-BE-1.

Exposes:
- `GET /pnl/series` — ordered performance points time series
- `GET /pnl/current` — latest performance snapshot
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.performance_repo import PerformanceRepository

router = APIRouter(tags=["pnl"])


class PerformancePointOut(BaseModel):
    id: int | None = None
    cycle_id: str
    portfolio_pnl: float
    hedge_pnl: float
    net_pnl: float
    drawdown: float
    hedge_cost: float
    benchmark_pnl: float
    ts: _dt.datetime | None = None


@router.get("/pnl/current", response_model=PerformancePointOut)
def get_current_pnl(
    engine: Engine = Depends(get_readback_engine),
) -> PerformancePointOut:
    """Return the latest performance snapshot."""
    repo = PerformanceRepository(engine)
    latest = repo.get_latest()
    if not latest:
        return PerformancePointOut(
            cycle_id="initial",
            portfolio_pnl=0.0,
            hedge_pnl=0.0,
            net_pnl=0.0,
            drawdown=0.0,
            hedge_cost=0.0,
            benchmark_pnl=0.0,
            ts=_dt.datetime.now(_dt.timezone.utc),
        )

    return PerformancePointOut(
        id=latest.id,
        cycle_id=latest.cycle_id,
        portfolio_pnl=float(latest.portfolio_pnl),
        hedge_pnl=float(latest.hedge_pnl),
        net_pnl=float(latest.net_pnl),
        drawdown=float(latest.drawdown),
        hedge_cost=float(latest.hedge_cost),
        benchmark_pnl=float(latest.benchmark_pnl),
        ts=latest.ts,
    )


@router.get("/pnl/series", response_model=list[PerformancePointOut])
def get_pnl_series(
    cycle_id: str | None = Query(default=None, description="Optional cycle filter"),
    limit: int = Query(default=100, ge=1, le=1000),
    engine: Engine = Depends(get_readback_engine),
) -> list[PerformancePointOut]:
    """Return ordered performance time series."""
    repo = PerformanceRepository(engine)
    series = repo.get_series(cycle_id=cycle_id, limit=limit)
    return [
        PerformancePointOut(
            id=r.id,
            cycle_id=r.cycle_id,
            portfolio_pnl=float(r.portfolio_pnl),
            hedge_pnl=float(r.hedge_pnl),
            net_pnl=float(r.net_pnl),
            drawdown=float(r.drawdown),
            hedge_cost=float(r.hedge_cost),
            benchmark_pnl=float(r.benchmark_pnl),
            ts=r.ts,
        )
        for r in series
    ]
