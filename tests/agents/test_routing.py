"""Conditional routing between orchestrator nodes — task P6-BE-7 / issue #153.

The ``deps``-wired graph turns the ``route_after_*`` functions into
``add_conditional_edges``. This exercises all three short-circuits end to end:

- ``NO_TRADE``  → after ``STRATEGY_EVALUATION``, skip ``RISK_CHECK`` + ``EXECUTION``;
- ``REASSESS``  → same skip;
- ``REJECT``    → after ``RISK_CHECK``, skip ``EXECUTION``;

and the happy path (``SELECT_STRATEGY`` → ``APPROVE``) still visits all six. The
``deps``-free skeleton stays a plain linear chain.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator import (
    OrchestratorDeps,
    build_orchestrator_graph,
    build_state_graph,
)

pytestmark = pytest.mark.integration

_INITIAL, _ANALYZING, _STRATEGY, _RISK, _EXECUTION, _MONITORING = (
    "INITIAL",
    "ANALYZING",
    "STRATEGY_EVALUATION",
    "RISK_CHECK",
    "EXECUTION",
    "MONITORING",
)


def _fake_llm(payload: dict[str, Any]) -> Any:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(payload)
    return fake


class _NeverBroker:
    def submit_order(self, _payload: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError("a skipped EXECUTION node reached the broker")


class _FillingBroker:
    """Echoes any submitted combo/single-leg payload back as fully filled."""

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = int(payload["qty"])
        price = {"buy": "3.20", "sell": "1.10"}
        if "legs" in payload:
            return {
                "id": "route-combo-1",
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
            "id": "route-single-1",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "qty": payload["qty"],
            "filled_qty": payload["qty"],
            "filled_avg_price": price.get(payload["side"], "2.00"),
            "status": "filled",
            "submitted_at": "2026-09-03T14:35:00Z",
            "filled_at": "2026-09-03T14:35:02Z",
        }


def _run(
    inputs: Callable[[str | None], AnalysisInputs],
    llm_payload: dict[str, Any],
    *,
    cycle_id: str,
    broker: Any | None = None,
) -> dict[str, Any]:
    deps = OrchestratorDeps(
        inputs_provider=inputs,
        llm_client=_fake_llm(llm_payload),
        broker=broker or _NeverBroker(),
        engine=None,
        preflight=False,
    )
    return build_orchestrator_graph(deps).invoke({"cycle_id": cycle_id})


def test_skeleton_stays_linear_but_the_wired_graph_branches() -> None:
    assert build_state_graph().branches == {}
    assert set(build_state_graph(OrchestratorDeps()).branches) == {
        _ANALYZING,
        _STRATEGY,
        _RISK,
    }


def test_no_trade_skips_risk_and_execution(analysis_inputs) -> None:
    final = _run(
        analysis_inputs,
        {
            "decision": "NO_TRADE",
            "selected_strategy": None,
            "rationale": "drawdown inside tolerance",
            "confidence": 0.9,
        },
        cycle_id="cyc-no-trade",
    )

    assert final["visited"] == [_INITIAL, _ANALYZING, _STRATEGY, _MONITORING]
    assert _RISK not in final["visited"] and _EXECUTION not in final["visited"]
    assert "risk_decision" not in final and "execution_result" not in final
    assert final["current_node"] == _MONITORING


def test_reassess_skips_risk_and_execution(analysis_inputs) -> None:
    final = _run(
        analysis_inputs,
        {
            "decision": "REASSESS",
            "selected_strategy": None,
            "rationale": "context looks stale; re-run analysis",
            "confidence": 0.6,
        },
        cycle_id="cyc-reassess",
    )

    assert final["visited"] == [_INITIAL, _ANALYZING, _STRATEGY, _MONITORING]
    assert final["current_node"] == _MONITORING


def test_reject_visits_risk_then_skips_execution(analysis_inputs) -> None:
    final = _run(
        analysis_inputs,
        {
            # one canned body: the manager reads decision / selected_strategy,
            # the risk agent reads verdict.
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PUT_SPREAD",
            "rationale": "defined-risk downside protection",
            "confidence": 0.9,
            "verdict": "REJECT",
            "violations": ["qualitative concern"],
        },
        cycle_id="cyc-reject",
    )

    assert final["visited"] == [_INITIAL, _ANALYZING, _STRATEGY, _RISK, _MONITORING]
    assert _EXECUTION not in final["visited"]
    assert "execution_result" not in final
    assert final["risk_decision"].verdict.value == "REJECT"


def test_approve_walks_the_full_pipeline(analysis_inputs) -> None:
    final = _run(
        analysis_inputs,
        {
            "decision": "SELECT_STRATEGY",
            "selected_strategy": "PUT_SPREAD",
            "rationale": "defined-risk downside protection",
            "confidence": 0.9,
            "verdict": "APPROVE",
        },
        cycle_id="cyc-approve",
        broker=_FillingBroker(),
    )

    assert final["visited"] == [
        _INITIAL,
        _ANALYZING,
        _STRATEGY,
        _RISK,
        _EXECUTION,
        _MONITORING,
    ]
