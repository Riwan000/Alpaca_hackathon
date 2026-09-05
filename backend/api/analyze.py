"""``POST /analyze`` — run the analysis chain, return a ``HedgeContext`` — task P3-BE-12.

One call = one analysis cycle (BRD §11):

1. :func:`~backend.agents.ingest.build_live_analysis_inputs` assembles the cycle's
   :class:`~backend.agents.context_builder.AnalysisInputs` from Alpaca + the
   market-data / news / option-chain integrations;
2. :func:`~backend.agents.assembler.assemble_hedge_context` runs the five Phase 3
   agents over it, writing one ``agent_runs`` row per agent (task P3-BE-11) and
   marking any failed section ``degraded`` instead of aborting (BRD §31);
3. the resulting :class:`~backend.models.hedge_context.PortfolioState` is persisted
   as a ``portfolio_snapshots`` row plus its ``positions`` in one transaction
   (task P3-DB-2), with the computed risk metrics alongside (task P3-DB-3);
4. the :class:`~backend.models.hedge_context.HedgeContext` is returned.

The database engine is the one shared by the read-back endpoints
(:func:`backend.api.readback.get_readback_engine`), so ``GET /portfolio/latest``
and ``GET /agent-runs?cycle_id=`` read back this cycle immediately. Both the
inputs builder and the engine are FastAPI dependencies the test suite overrides.
"""

from __future__ import annotations

import decimal
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from backend.agents.assembler import assemble_hedge_context
from backend.agents.context_builder import AnalysisInputs
from backend.agents.ingest import IngestError, build_live_analysis_inputs
from backend.api.readback import get_readback_engine
from backend.db.agent_runs_repo import AgentRunRepository
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)
from backend.models.hedge_context import HedgeContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])


def provide_analysis_inputs(
    engine: Engine = Depends(get_readback_engine),
) -> AnalysisInputs:
    """Build the live inputs bundle for one cycle (overridden in tests).

    Passes ``engine`` through so ``current_hedge`` reflects the hedge actually
    on the book (:func:`~backend.agents.ingest.reconstruct_current_hedge`)
    rather than always defaulting to empty.
    """
    try:
        return build_live_analysis_inputs(engine=engine)
    except IngestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _dec(value: Any) -> decimal.Decimal:
    return decimal.Decimal(str(float(value)))


def _dec_opt(value: Any) -> decimal.Decimal | None:
    return None if value is None else _dec(value)


def _persist_snapshot(engine: Engine, ctx: HedgeContext) -> None:
    """Write this cycle's snapshot + positions + risk metrics (P3-DB-2 / P3-DB-3)."""
    state = ctx.portfolio_state
    repo = PortfolioSnapshotRepository(engine)
    snapshot = PortfolioSnapshotRecord(
        cycle_id=ctx.cycle_id,
        total_value=_dec(state.total_value),
        cash=_dec(state.cash),
        equity=_dec(state.equity),
        buying_power=_dec(state.buying_power),
        volatility=_dec_opt(state.volatility),
        beta=_dec_opt(state.beta),
        drawdown=_dec_opt(state.drawdown),
        ts=ctx.timestamp,
    )
    positions = [
        PositionRecord(
            symbol=p.symbol,
            qty=_dec(p.qty),
            avg_price=_dec(abs(p.avg_price)),
            market_value=_dec(p.market_value),
            asset_class=p.asset_class.value,
            side=p.side.value,
        )
        for p in state.positions
    ]
    repo.save_with_positions(snapshot, positions)


@router.post("/analyze", response_model=HedgeContext)
def analyze(
    inputs: AnalysisInputs = Depends(provide_analysis_inputs),
    engine: Engine = Depends(get_readback_engine),
) -> HedgeContext:
    """Run one analysis cycle and return the assembled :class:`HedgeContext`."""
    run_repo = AgentRunRepository(engine)
    ctx = assemble_hedge_context(inputs, run_repo=run_repo)
    try:
        _persist_snapshot(engine, ctx)
    except Exception as exc:  # noqa: BLE001 - a persistence failure must not lose the context
        logger.exception("failed to persist snapshot for cycle %s", ctx.cycle_id)
        raise HTTPException(
            status_code=500, detail=f"analysis ran but persistence failed: {exc}"
        ) from exc
    return ctx
