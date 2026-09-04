"""State-persistence hook on every node transition — task P6-BE-10 / issue #156.

Every node ENTER and EXIT writes a timestamped ``workflow_state`` row (and a
``workflow_transitions`` row). After a cycle:

- ``select current_node, updated_at from workflow_state`` shows each step, in
  order, every row carrying an ``updated_at``;
- the transition log pairs an ``ENTER`` with an ``EXIT`` per visited node;
- a node the router skipped leaves no rows.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.orchestrator import (
    OrchestratorDeps,
    build_orchestrator_graph,
)
from backend.agents.orchestrator.persistence import (
    RecordingSink,
    TransitionPhase,
    with_transition_hook,
)
from backend.db.workflow_repo import WorkflowRepository

pytestmark = pytest.mark.integration


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


class _FillingBroker:
    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = int(payload["qty"])
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:
            return {
                "id": "hook-combo-1",
                "status": "filled",
                "submitted_at": "2026-09-03T14:35:00Z",
                "filled_at": "2026-09-03T14:35:02Z",
                "legs": [
                    {
                        "symbol": leg["symbol"],
                        "side": leg["side"],
                        "qty": str(int(leg["ratio_qty"]) * base),
                        "filled_qty": str(int(leg["ratio_qty"]) * base),
                        "filled_avg_price": price.get(leg["side"], "2.00"),
                        "status": "filled",
                        "filled_at": "2026-09-03T14:35:01Z",
                    }
                    for leg in payload["legs"]
                ],
            }
        return {
            "id": "hook-single-1",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "qty": payload["qty"],
            "filled_qty": payload["qty"],
            "filled_avg_price": price.get(payload["side"], "2.00"),
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
        }


def test_with_transition_hook_brackets_the_body_with_enter_and_exit() -> None:
    sink = RecordingSink()
    body = lambda state: {"current_node": "ANALYZING", "visited": ["ANALYZING"], "route": "STRATEGY_EVALUATION"}  # noqa: E731
    wrapped = with_transition_hook("ANALYZING", body, sink)

    out = wrapped({"cycle_id": "cyc-unit"})

    assert out["current_node"] == "ANALYZING"  # body result passes straight through
    phases = [(node, phase, status) for (_cid, node, phase, status, _d) in sink.calls]
    assert phases == [
        ("ANALYZING", TransitionPhase.ENTER, "RUNNING"),
        ("ANALYZING", TransitionPhase.EXIT, "RUNNING"),
    ]
    assert sink.calls[-1][4] == {"route": "STRATEGY_EVALUATION"}


def test_halted_body_exits_with_halted_status() -> None:
    sink = RecordingSink()
    body = lambda state: {"current_node": "RISK_CHECK", "halted": True, "route": "MONITORING", "failure_class": "CRITICAL"}  # noqa: E731

    with_transition_hook("RISK_CHECK", body, sink)({"cycle_id": "cyc-halt"})

    assert sink.calls[0][3] == "RUNNING"      # ENTER
    assert sink.calls[1][2] is TransitionPhase.EXIT
    assert sink.calls[1][3] == "HALTED"


def test_every_transition_is_persisted_with_a_timestamp(migrated_engine, analysis_inputs) -> None:
    deps = OrchestratorDeps(
        inputs_provider=analysis_inputs,
        llm_client=_fake_llm(
            {
                "decision": "SELECT_STRATEGY",
                "selected_strategy": "PUT_SPREAD",
                "rationale": "defined-risk downside protection",
                "confidence": 0.9,
                "verdict": "APPROVE",
            }
        ),
        broker=_FillingBroker(),
        engine=migrated_engine,
        preflight=False,
    )

    build_orchestrator_graph(deps).invoke({"cycle_id": "cyc-hook"})

    repo = WorkflowRepository(migrated_engine)
    transitions = repo.get_transitions("cyc-hook")

    # one ENTER + one EXIT for each of the six nodes, in pipeline order
    seen = [(t.to_node, (t.detail or {}).get("phase")) for t in transitions]
    assert seen == [
        ("INITIAL", "ENTER"), ("INITIAL", "EXIT"),
        ("ANALYZING", "ENTER"), ("ANALYZING", "EXIT"),
        ("STRATEGY_EVALUATION", "ENTER"), ("STRATEGY_EVALUATION", "EXIT"),
        ("RISK_CHECK", "ENTER"), ("RISK_CHECK", "EXIT"),
        ("EXECUTION", "ENTER"), ("EXECUTION", "EXIT"),
        ("MONITORING", "ENTER"), ("MONITORING", "EXIT"),
    ]
    assert all(t.transitioned_at is not None for t in transitions)

    # the mirror on workflow_state: latest row per step, each with updated_at
    final = repo.get_state("cyc-hook")
    assert final is not None and final.current_node == "MONITORING"
    assert final.updated_at is not None


def test_a_skipped_node_leaves_no_transition_rows(migrated_engine, analysis_inputs) -> None:
    deps = OrchestratorDeps(
        inputs_provider=analysis_inputs,
        llm_client=_fake_llm(
            {"decision": "NO_TRADE", "selected_strategy": None, "rationale": "no", "confidence": 0.9}
        ),
        engine=migrated_engine,
        preflight=False,
    )

    build_orchestrator_graph(deps).invoke({"cycle_id": "cyc-hook-skip"})

    nodes_touched = {
        t.to_node for t in WorkflowRepository(migrated_engine).get_transitions("cyc-hook-skip")
    }
    assert nodes_touched == {"INITIAL", "ANALYZING", "STRATEGY_EVALUATION", "MONITORING"}
    assert "RISK_CHECK" not in nodes_touched and "EXECUTION" not in nodes_touched
