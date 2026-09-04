"""``EXECUTION`` node — task P6-BE-5 / issue #151.

Confirms the node wraps Phase 5 execution:
- an approved decision + a filling broker writes an :class:`ExecutionResult` to
  the state and an ``orders`` row to the DB;
- a broker rejection is a truthful ``FAILED`` result recorded in state and in
  ``execution_failures`` — not swallowed, not raised;
- a stale context aborts at pre-flight with **no order sent**;
- a re-invoke on a cycle that already has an order does not submit a second one.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.orchestrator.nodes import (
    OrchestratorDeps,
    execution_node,
    risk_check_node,
    strategy_evaluation_node,
)
from backend.db.execution_failures_repo import ExecutionFailureRepository
from backend.db.orders_repo import OrderRepository
from backend.integrations.alpaca.client import AlpacaError
from backend.models.enums import ExecutionStatus

pytestmark = pytest.mark.integration


class _FillingBroker:
    """Echoes the submitted mleg payload back as a fully-filled combo order."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        base = int(payload["qty"])
        fill_price = {"buy": "3.20", "sell": "1.90"}
        legs = [
            {
                "symbol": leg["symbol"],
                "side": leg["side"],
                "qty": str(int(leg["ratio_qty"]) * base),
                "filled_qty": str(int(leg["ratio_qty"]) * base),
                "filled_avg_price": fill_price[leg["side"]],
                "status": "filled",
                "filled_at": "2026-09-03T14:35:01Z",
            }
            for leg in payload["legs"]
        ]
        return {
            "id": "combo-node-1",
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
            "legs": legs,
        }


class _RejectingBroker:
    def submit_order(self, _payload: dict[str, Any]) -> dict[str, Any]:
        raise AlpacaError("insufficient buying power")


class _AcceptsButUnmappableBroker:
    """Accepts the submission but reports a still-working, non-terminal order —
    the order is live yet ``build_execution_result`` cannot map it."""

    def __init__(self) -> None:
        self.calls = 0

    def submit_order(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"id": f"live-{self.calls}", "status": "accepted", "legs": []}


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


def _approved_state(golden_hedge_context, engine) -> dict[str, Any]:
    """Chain strategy + risk nodes → a state carrying an APPROVE ``risk_decision``
    for the (multi-leg) PUT_SPREAD family."""
    base = {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    strat = strategy_evaluation_node(
        OrchestratorDeps(
            llm_client=_fake_llm(
                {
                    "decision": "SELECT_STRATEGY",
                    "selected_strategy": "PUT_SPREAD",
                    "rationale": "defined-risk downside protection",
                    "confidence": 0.9,
                }
            )
        )
    )
    state = {**base, **strat(base)}
    risk = risk_check_node(
        OrchestratorDeps(engine=engine, llm_client=_fake_llm({"verdict": "APPROVE", "rationale": "clean"}))
    )
    return {**state, **risk(state)}


def test_approved_decision_fills_and_persists_an_order(
    migrated_engine, golden_hedge_context
) -> None:
    state = _approved_state(golden_hedge_context, migrated_engine)
    assert state["risk_decision"].verdict.value == "APPROVE"
    node = execution_node(
        OrchestratorDeps(engine=migrated_engine, broker=_FillingBroker(), preflight=False)
    )

    out = node(state)

    result = out["execution_result"]
    assert result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED)
    assert out["current_node"] == "EXECUTION"
    assert "errors" not in out
    assert OrderRepository(migrated_engine).list_for_cycle(golden_hedge_context.cycle_id)


def test_broker_rejection_is_a_truthful_failed_result_not_swallowed(
    migrated_engine, golden_hedge_context
) -> None:
    state = _approved_state(golden_hedge_context, migrated_engine)
    node = execution_node(
        OrchestratorDeps(engine=migrated_engine, broker=_RejectingBroker(), preflight=False)
    )

    out = node(state)  # must not raise

    result = out["execution_result"]
    assert result.status is ExecutionStatus.FAILED
    assert result.error and "insufficient buying power" in result.error
    assert any("EXECUTION" in e for e in out["errors"])
    assert ExecutionFailureRepository(migrated_engine).list_for_cycle(golden_hedge_context.cycle_id)
    assert OrderRepository(migrated_engine).count() == 0


def test_stale_context_aborts_at_preflight_with_no_order(
    migrated_engine, golden_hedge_context
) -> None:
    state = _approved_state(golden_hedge_context, migrated_engine)
    node = execution_node(
        OrchestratorDeps(engine=migrated_engine, broker=_FillingBroker(), preflight=True)
    )

    out = node(state)

    result = out["execution_result"]
    assert result.status is ExecutionStatus.FAILED
    assert "pre-flight abort" in result.error
    assert OrderRepository(migrated_engine).count() == 0


def test_broker_accepts_but_unmappable_result_still_blocks_a_re_submit(
    migrated_engine, golden_hedge_context
) -> None:
    """The broker took the order but the response can't be mapped to a terminal
    result — the order is live, so an ``orders`` row must still be written and a
    re-invoke must not place a second one."""
    state = _approved_state(golden_hedge_context, migrated_engine)
    broker = _AcceptsButUnmappableBroker()
    node = execution_node(
        OrchestratorDeps(engine=migrated_engine, broker=broker, preflight=False)
    )

    first = node(state)
    assert first["execution_result"].status is ExecutionStatus.FAILED
    assert first["execution_result"].broker_order_id == "live-1"
    assert OrderRepository(migrated_engine).list_for_cycle(golden_hedge_context.cycle_id)

    second = node(state)
    assert broker.calls == 1  # no second live order
    assert "execution_result" not in second
    assert any("already on file" in note for note in second["notes"])


def test_re_invoke_does_not_submit_a_second_order(
    migrated_engine, golden_hedge_context
) -> None:
    state = _approved_state(golden_hedge_context, migrated_engine)
    broker = _FillingBroker()
    node = execution_node(
        OrchestratorDeps(engine=migrated_engine, broker=broker, preflight=False)
    )

    node(state)
    second = node(state)

    assert len(broker.payloads) == 1
    assert "execution_result" not in second
    assert any("already on file" in note for note in second["notes"])
    assert len(OrderRepository(migrated_engine).list_for_cycle(golden_hedge_context.cycle_id)) == 1
