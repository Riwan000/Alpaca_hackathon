"""``POST /strategy/evaluate`` — task P4-BE-11 (BRD §15–18).

One call = one strategy-evaluation cycle:

1. Accept a :class:`~backend.models.hedge_context.HedgeContext` (JSON body).
2. Run all four strategy agents
   (:class:`~backend.agents.strategies.ProtectivePutAgent`,
   :class:`~backend.agents.strategies.PutSpreadAgent`,
   :class:`~backend.agents.strategies.CollarAgent`,
   :class:`~backend.agents.strategies.NoHedgeAgent`) — one hypothesis each.
3. Pre-filter the hypotheses via :func:`~backend.agents.strategies.prefilter`.
4. Run :class:`~backend.agents.strategies.StrategyManager` (validate → compare →
   select) to produce one :class:`~backend.models.strategy.StrategyDecision`.
5. Persist **all four hypotheses** (including rejected / NOT_VIABLE ones) plus the
   decision in the strategy tables using
   :class:`~backend.db.strategy_repo.StrategyHypothesisRepository` and
   :class:`~backend.db.strategy_repo.StrategyDecisionRepository`.
6. Return the :class:`~backend.models.strategy.StrategyDecision`.

The database engine is shared with the read-back endpoints
(:func:`backend.api.readback.get_readback_engine`), so the GETs in
:mod:`backend.api.strategy_readback` see this cycle's data immediately.

The LLM client is injectable via a FastAPI dependency so the test suite can swap
it for a :class:`~tests.conftest.FakeLLMClient` without network traffic.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from backend.agents.strategies import (
    CollarAgent,
    NoHedgeAgent,
    ProtectivePutAgent,
    PutSpreadAgent,
    StrategyManager,
    prefilter,
)
from backend.api.readback import get_readback_engine
from backend.db.strategy_repo import (
    StrategyDecisionRecord,
    StrategyDecisionRepository,
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyDecision, StrategyHypothesis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strategy"])

# ---------------------------------------------------------------------------
# LLM client dependency (overridden in tests)
# ---------------------------------------------------------------------------


def get_strategy_llm_client() -> Any:
    """Return None — the StrategyManager resolves its own client from config.

    Tests override this to inject a :class:`~tests.conftest.FakeLLMClient`.
    """
    return None


# ---------------------------------------------------------------------------
# DB mapping helpers
# ---------------------------------------------------------------------------


def _hypothesis_record(hyp: StrategyHypothesis) -> StrategyHypothesisRecord:
    """Convert a :class:`StrategyHypothesis` to a DB record."""
    verdict = "ACCEPTED" if hyp.viable else "REJECTED"
    # Use mode="json" so Pydantic serializes date/datetime to ISO strings,
    # which SQLite's JSON column stores without a TypeError.
    legs = [leg.model_dump(mode="json") for leg in hyp.legs] if hyp.legs else None
    metrics: dict[str, Any] = {}
    m = hyp.hedge_metrics
    if m.cost_pct_of_portfolio is not None:
        metrics["cost_pct_of_portfolio"] = m.cost_pct_of_portfolio
    if m.downside_protection_pct is not None:
        metrics["downside_protection_pct"] = m.downside_protection_pct
    if m.hedge_ratio is not None:
        metrics["hedge_ratio"] = m.hedge_ratio
    return StrategyHypothesisRecord(
        cycle_id=hyp.cycle_id,
        strategy_type=hyp.strategy.value,
        verdict=verdict,
        legs=legs or None,
        metrics=metrics or None,
        rejection_reason=hyp.rejection_reason,
    )


def _decision_record(
    decision: StrategyDecision,
    selected_hypothesis_id: int | None,
) -> StrategyDecisionRecord:
    """Convert a :class:`StrategyDecision` to a DB record."""
    alternatives: list[dict[str, Any]] = [
        {
            "strategy": h.strategy.value,
            "viable": h.viable,
            "cost": h.cost,
            "rationale": h.rationale,
        }
        for h in decision.alternatives
    ]
    comparison: list[dict[str, Any]] = [
        {
            "strategy": row.strategy.value,
            "cost": row.cost,
            "downside_protection_pct": row.downside_protection_pct,
            "upside_giveup_pct": row.upside_giveup_pct,
            "liquidity": row.liquidity,
        }
        for row in decision.comparison
    ]
    return StrategyDecisionRecord(
        cycle_id=decision.cycle_id,
        action=decision.decision.value,
        rationale=decision.rationale,
        selected_hypothesis_id=selected_hypothesis_id,
        alternatives=alternatives or None,
        comparison=comparison or None,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/strategy/evaluate", response_model=StrategyDecision)
def strategy_evaluate(
    context: HedgeContext,
    engine: Engine = Depends(get_readback_engine),
    llm_client: Any = Depends(get_strategy_llm_client),
) -> StrategyDecision:
    """Run the full strategy layer for ``context`` and return the decision.

    Runs all four hedge-family agents, pre-filters their hypotheses, then passes
    the surviving set to the :class:`~backend.agents.strategies.StrategyManager`
    (validate → compare → select). All four hypotheses and the decision are
    persisted before the response is returned.

    Returns:
        The :class:`~backend.models.strategy.StrategyDecision` (200 on success).

    Raises:
        HTTPException 500: when the strategy layer raises an unexpected error or
            persistence fails.
    """
    # ------------------------------------------------------------------
    # Stage A — run the four strategy agents
    # ------------------------------------------------------------------
    agents = [
        ProtectivePutAgent(),
        PutSpreadAgent(),
        CollarAgent(),
        NoHedgeAgent(),
    ]
    try:
        hypotheses = [agent.propose(context) for agent in agents]
    except Exception as exc:
        logger.exception(
            "strategy_evaluate: agent error for cycle %s", context.cycle_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"strategy agent error: {exc}",
        ) from exc

    # ------------------------------------------------------------------
    # Stage B — pre-filter
    # ------------------------------------------------------------------
    try:
        prefilter_result = prefilter(hypotheses, context)
    except Exception as exc:
        logger.exception(
            "strategy_evaluate: prefilter error for cycle %s", context.cycle_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"prefilter error: {exc}",
        ) from exc

    # ------------------------------------------------------------------
    # Stage C — StrategyManager (validate → compare → select)
    # ------------------------------------------------------------------
    try:
        manager = StrategyManager(client=llm_client)
        decision = manager.run(prefilter_result, context)
    except Exception as exc:
        logger.exception(
            "strategy_evaluate: manager error for cycle %s", context.cycle_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"strategy manager error: {exc}",
        ) from exc

    # ------------------------------------------------------------------
    # Stage D — persist hypotheses + decision
    # ------------------------------------------------------------------
    try:
        hypo_repo = StrategyHypothesisRepository(engine)
        dec_repo = StrategyDecisionRepository(engine)

        # Persist all four hypotheses (viable and not)
        records = [_hypothesis_record(h) for h in hypotheses]
        saved = hypo_repo.save_many(records)

        # Locate the persisted ID of the selected hypothesis (if any)
        selected_id: int | None = None
        if decision.selected_hypothesis is not None:
            # Match by strategy type and cycle_id among saved records
            for saved_rec in saved:
                if (
                    saved_rec.strategy_type
                    == decision.selected_hypothesis.strategy.value
                ):
                    selected_id = saved_rec.id
                    break

        dec_repo.create(_decision_record(decision, selected_id))
    except Exception as exc:
        logger.exception(
            "strategy_evaluate: persistence error for cycle %s", context.cycle_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"strategy evaluation succeeded but persistence failed: {exc}",
        ) from exc

    return decision
