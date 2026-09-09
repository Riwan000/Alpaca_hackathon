"""P&L and Performance read-back endpoints — tasks P8-BE-1, P8-BE-2.

Exposes:
- `GET /pnl/series` — ordered performance points time series
- `GET /pnl/current` — latest performance snapshot
- `GET /pnl/vs-benchmark` — hedged vs unhedged-benchmark comparison (BRD §36)
"""

from __future__ import annotations

import datetime as _dt

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.config import Settings, get_settings
from backend.db.performance_repo import PerformanceRepository
from backend.integrations.alpaca.client import AlpacaClient, resolve_alpaca_config

router = APIRouter(tags=["pnl"])


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


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
    settings: Settings = Depends(get_settings),
) -> PerformancePointOut:
    """Return the latest performance snapshot."""
    repo = PerformanceRepository(engine)
    latest = repo.get_latest()
    if not latest:
        try:
            resolve_alpaca_config(settings)
            client = AlpacaClient(settings)
            with client:
                account = client.get_account()
                positions = client.get_positions()
            portfolio_val = _f(account.get("portfolio_value") or account.get("equity"))
            last_equity = _f(account.get("last_equity") or portfolio_val)
            day_pnl = round(portfolio_val - last_equity, 2)
            total_unrealized_pl = round(sum(_f(p.get("unrealized_pl")) for p in (positions or [])), 2)
            drawdown = round((portfolio_val - last_equity) / last_equity, 6) if last_equity and portfolio_val < last_equity else 0.0
            return PerformancePointOut(
                cycle_id="alpaca-live",
                portfolio_pnl=total_unrealized_pl if total_unrealized_pl != 0 else day_pnl,
                hedge_pnl=0.0,
                net_pnl=day_pnl if day_pnl != 0 else total_unrealized_pl,
                drawdown=drawdown,
                hedge_cost=0.0,
                benchmark_pnl=day_pnl if day_pnl != 0 else total_unrealized_pl,
                ts=_dt.datetime.now(_dt.timezone.utc),
            )
        except Exception:
            pass

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
    settings: Settings = Depends(get_settings),
) -> list[PerformancePointOut]:
    """Return ordered performance time series."""
    repo = PerformanceRepository(engine)
    series = repo.get_series(cycle_id=cycle_id, limit=limit)
    if not series and not cycle_id:
        try:
            resolve_alpaca_config(settings)
            client = AlpacaClient(settings)
            with client:
                hist = client.get_portfolio_history(period="1W", timeframe="1H")
            base_val = _f(hist.get("base_value"), default=100000.0)
            timestamps = hist.get("timestamp") or []
            equities = hist.get("equity") or []
            profits = hist.get("profit_loss") or []
            peak = base_val
            out_points: list[PerformancePointOut] = []
            for i, (ts, eq, pl) in enumerate(zip(timestamps, equities, profits)):
                eq_val = _f(eq, base_val)
                pl_val = _f(pl)
                if eq_val > peak:
                    peak = eq_val
                dd = round((eq_val - peak) / peak, 6) if peak > 0 else 0.0
                try:
                    dt_val = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
                except Exception:
                    dt_val = _dt.datetime.now(_dt.timezone.utc)
                out_points.append(
                    PerformancePointOut(
                        id=i + 1,
                        cycle_id=f"alpaca-{i}",
                        portfolio_pnl=pl_val,
                        hedge_pnl=0.0,
                        net_pnl=pl_val,
                        drawdown=dd,
                        hedge_cost=0.0,
                        benchmark_pnl=pl_val,
                        ts=dt_val,
                    )
                )
            if out_points:
                return out_points
        except Exception:
            pass

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
