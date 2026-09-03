"""Read-back endpoints — task P3-DB-4.

Two GETs that let the dashboard (and ``curl``) read what an analysis pass wrote:

* ``GET /portfolio/latest`` — the newest ``portfolio_snapshots`` row, its risk
  metrics, and its position rows. Backs ``PortfolioOverview`` (P3-FE-1) and
  ``RiskOverview`` (P3-FE-2).
* ``GET /agent-runs?cycle_id=`` — that cycle's ``agent_runs`` in ``started_at``
  order; without ``cycle_id``, every run. Backs the ``AgentActivity`` timeline
  (P3-FE-3).

Both read through the synchronous repositories
(:class:`~backend.db.repository.PortfolioSnapshotRepository`,
:class:`~backend.db.agent_runs_repo.AgentRunRepository`) over a sync
:class:`~sqlalchemy.engine.Engine` supplied by :func:`get_readback_engine` — a
FastAPI dependency the test suite overrides to point at a scratch database.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.db.agent_runs_repo import AgentRunRepository
from backend.db.repository import PortfolioSnapshotRepository

router = APIRouter(tags=["readback"])

_engine: Engine | None = None


def get_readback_engine() -> Engine:
    """Return a process-wide synchronous Engine for the read-back repositories.

    Built lazily from :attr:`Settings.database_url` so importing this module (and
    ``create_app()``) never needs a configured database. Tests override this
    dependency with an engine bound to their migrated scratch DB.
    """
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine

        from backend.config import get_settings
        from backend.db import normalize_driver

        url = normalize_driver(get_settings().database_url.get_secret_value())
        _engine = create_engine(url, future=True)
    return _engine


class PositionOut(BaseModel):
    symbol: str
    qty: float
    avg_price: float
    market_value: float
    asset_class: str
    side: str


class PortfolioLatestOut(BaseModel):
    id: int
    cycle_id: str
    ts: _dt.datetime
    total_value: float
    cash: float
    equity: float
    buying_power: float
    volatility: float | None = None
    beta: float | None = None
    drawdown: float | None = None
    positions: list[PositionOut]


class AgentRunOut(BaseModel):
    id: int
    cycle_id: str
    agent_name: str
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None
    started_at: _dt.datetime
    finished_at: _dt.datetime | None = None
    duration_ms: int | None = None


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


@router.get("/portfolio/latest", response_model=PortfolioLatestOut)
def portfolio_latest(
    engine: Engine = Depends(get_readback_engine),
) -> PortfolioLatestOut:
    """The most recent portfolio snapshot with its risk metrics and positions."""
    repo = PortfolioSnapshotRepository(engine)
    snapshot = repo.latest()
    if snapshot is None or snapshot.id is None:
        raise HTTPException(status_code=404, detail="no portfolio snapshot recorded yet")

    positions = repo.positions_for(snapshot.id)
    return PortfolioLatestOut(
        id=snapshot.id,
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
            PositionOut(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_price=float(p.avg_price),
                market_value=float(p.market_value),
                asset_class=p.asset_class,
                side=p.side,
            )
            for p in positions
        ],
    )


@router.get("/agent-runs", response_model=list[AgentRunOut])
def agent_runs(
    cycle_id: str | None = Query(
        default=None, description="restrict to one analysis cycle"
    ),
    engine: Engine = Depends(get_readback_engine),
) -> list[AgentRunOut]:
    """Agent runs in ``started_at`` order, optionally filtered to one cycle."""
    repo = AgentRunRepository(engine)
    runs = repo.list_for_cycle(cycle_id) if cycle_id is not None else repo.list_all()
    return [
        AgentRunOut(
            id=run.id,  # type: ignore[arg-type]  # persisted rows always carry an id
            cycle_id=run.cycle_id,
            agent_name=run.agent_name,
            inputs=run.inputs,
            outputs=run.outputs,
            error=run.error,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
        )
        for run in runs
    ]
