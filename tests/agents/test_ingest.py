"""``reconstruct_current_hedge`` — rebuilding ``current_hedge`` from order history.

``AnalysisInputs.current_hedge`` otherwise always defaults to empty — nothing
populates it from the DB, so the monitor/hedge logic never sees a hedge that
genuinely exists even though positions are live-refetched from Alpaca every
pass. These tests drive :func:`backend.agents.ingest.reconstruct_current_hedge`
directly against a migrated scratch database (the ``migrated_engine`` fixture
from ``tests/agents/conftest.py``):

* the most recent actioned cycle is a ``NEW_HEDGE`` with a ``FILLED`` order ->
  an active hedge with the correct legs / strategy type / cost basis;
* a cycle with no orders (``MAINTAIN`` / ``NO_TRADE``) is skipped in favor of an
  earlier actioned cycle;
* the most recent actioned cycle is a ``REMOVE`` -> empty, even though an
  earlier cycle opened a hedge;
* no history at all -> empty;
* a DB error (unmigrated engine) -> degrades to empty rather than raising.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.agents.ingest import reconstruct_current_hedge
from backend.db.orders_repo import FillRecord, OrderRecord, OrderRepository
from backend.db.strategy_repo import (
    StrategyDecisionRecord,
    StrategyDecisionRepository,
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)
from backend.models.enums import StrategyType

pytestmark = pytest.mark.integration


def _leg(
    *,
    underlying: str = "AAPL",
    right: str = "PUT",
    side: str = "BUY",
    strike: float = 145.0,
    expiration: str = "2026-10-03",
    quantity: int = 2,
) -> dict:
    """One ``orders.legs`` JSONB entry, shaped exactly like
    ``OptionLeg.model_dump(mode="json")`` (see
    ``backend.agents.execution.result.persist_execution_result``)."""
    return {
        "underlying": underlying,
        "right": right,
        "side": side,
        "strike": strike,
        "expiration": expiration,
        "quantity": quantity,
        "limit_price": None,
        "occ_symbol": None,
    }


def _new_hedge_cycle(
    engine: Engine,
    cycle_id: str,
    *,
    strategy_type: str = "PROTECTIVE_PUT",
    order_status: str = "FILLED",
    legs: list[dict] | None = None,
) -> None:
    """Persist a hypothesis + ``NEW_HEDGE`` decision + order (with a fill) for
    one cycle, the shape a real Strategy Manager -> Execution pass writes."""
    legs = legs if legs is not None else [_leg()]
    hyp = StrategyHypothesisRepository(engine).create(
        StrategyHypothesisRecord(
            cycle_id=cycle_id,
            strategy_type=strategy_type,
            verdict="ACCEPTED",
            legs=legs,
            metrics={"hedge_ratio": 0.8},
        )
    )
    StrategyDecisionRepository(engine).create(
        StrategyDecisionRecord(
            cycle_id=cycle_id,
            action="NEW_HEDGE",
            rationale="test fixture",
            selected_hypothesis_id=hyp.id,
        )
    )
    order = OrderRecord(cycle_id=cycle_id, order_class="SINGLE", status=order_status, legs=legs)
    fills = [
        FillRecord(order_id=0, leg_symbol="AAPL251003P00145000", qty=Decimal(str(leg["quantity"])), price=Decimal("3.15"))
        for leg in legs
    ]
    OrderRepository(engine).save_with_fills(order, fills)


def _no_op_cycle(engine: Engine, cycle_id: str, *, action: str = "MAINTAIN") -> None:
    """A decision with no resulting order — ``MAINTAIN`` / ``NO_TRADE``."""
    StrategyDecisionRepository(engine).create(
        StrategyDecisionRecord(cycle_id=cycle_id, action=action, rationale="nothing to do")
    )


def _remove_cycle(engine: Engine, cycle_id: str) -> None:
    """A ``REMOVE`` decision with a filled closing order."""
    StrategyDecisionRepository(engine).create(
        StrategyDecisionRecord(cycle_id=cycle_id, action="REMOVE", rationale="closing the hedge")
    )
    closing_leg = _leg(side="SELL")
    order = OrderRecord(cycle_id=cycle_id, order_class="SINGLE", status="FILLED", legs=[closing_leg])
    OrderRepository(engine).save_with_fills(
        order, [FillRecord(order_id=0, leg_symbol="AAPL251003P00145000", qty=Decimal("2"), price=Decimal("3.00"))]
    )


def test_new_hedge_with_filled_order_is_active(migrated_engine: Engine) -> None:
    _new_hedge_cycle(migrated_engine, "cyc-1")

    hedge = reconstruct_current_hedge(migrated_engine)

    assert hedge.active is True
    assert hedge.strategy_type is StrategyType.PROTECTIVE_PUT
    assert len(hedge.legs) == 1
    assert hedge.legs[0].strike == 145.0
    assert hedge.legs[0].quantity == 2
    assert hedge.expiration == date(2026, 10, 3)
    assert hedge.cost_basis == pytest.approx(2 * 3.15)


def test_maintain_cycle_with_no_orders_is_skipped(migrated_engine: Engine) -> None:
    """A later ``MAINTAIN`` that never resulted in an order does not shadow the
    earlier cycle that actually opened the hedge on the book."""
    _new_hedge_cycle(migrated_engine, "cyc-1")
    _no_op_cycle(migrated_engine, "cyc-2", action="MAINTAIN")

    hedge = reconstruct_current_hedge(migrated_engine)

    assert hedge.active is True
    assert hedge.strategy_type is StrategyType.PROTECTIVE_PUT


def test_most_recent_remove_returns_empty(migrated_engine: Engine) -> None:
    """A REMOVE at the most recent actioned cycle means the hedge is closed —
    even though an earlier cycle opened one."""
    _new_hedge_cycle(migrated_engine, "cyc-1")
    _remove_cycle(migrated_engine, "cyc-2")

    hedge = reconstruct_current_hedge(migrated_engine)

    assert hedge.active is False
    assert hedge.legs == []


def test_no_history_returns_empty(migrated_engine: Engine) -> None:
    hedge = reconstruct_current_hedge(migrated_engine)

    assert hedge.active is False
    assert hedge.legs == []


def test_db_error_degrades_to_empty() -> None:
    """An unmigrated / unreachable database must never raise into the caller —
    it degrades to the safe empty default (BRD §31 pattern)."""
    broken_engine = create_engine("sqlite:///:memory:", future=True)

    hedge = reconstruct_current_hedge(broken_engine)

    assert hedge.active is False
    assert hedge.legs == []
