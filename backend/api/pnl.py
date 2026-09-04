"""P&L and Performance read-back endpoints — tasks P8-BE-1, P8-BE-2.

Exposes:
- `GET /pnl/series` — ordered performance points time series
- `GET /pnl/current` — latest performance snapshot
- `GET /pnl/vs-benchmark` — hedged vs unhedged-benchmark comparison (BRD §36)
"""

from __future__ import annotations

import datetime as _dt

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


class BenchmarkPointOut(BaseModel):
    ts: _dt.datetime | None = None
    cycle_id: str
    hedged_pnl: float
    unhedged_pnl: float
    hedge_cushion: float
    hedged_drawdown: float
    unhedged_drawdown: float


class BenchmarkComparisonOut(BaseModel):
    points: list[BenchmarkPointOut]
    hedged_max_drawdown: float
    unhedged_max_drawdown: float
    drawdown_reduction: float
    hedge_cushion: float
    hedge_cost: float
    is_cushioned: bool


@router.get("/pnl/vs-benchmark", response_model=BenchmarkComparisonOut)
def get_pnl_vs_benchmark(
    limit: int = Query(default=100, ge=1, le=1000),
    engine: Engine = Depends(get_readback_engine),
) -> BenchmarkComparisonOut:
    """Hedged portfolio vs unhedged benchmark, showing the hedge cushioning a drawdown.

    Before any hedge is on, the hedged and unhedged curves coincide; once a
    protective put pays off inside a drop, ``hedged_max_drawdown`` falls below
    ``unhedged_max_drawdown`` and ``is_cushioned`` is ``True`` (BRD §36).
    """
    repo = PerformanceRepository(engine)
    return BenchmarkComparisonOut.model_validate(repo.get_benchmark_comparison(limit=limit))
