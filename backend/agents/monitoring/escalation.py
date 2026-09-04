"""Level-2 escalation — re-enter the orchestrator at ``STRATEGY_EVALUATION`` (task P7-BE-5).

A fired Level-1 trigger does not just raise an alert — it starts a fresh
reassessment cycle. That cycle skips ``ANALYZING`` (the context it needs is
already in hand) and re-enters the graph at ``STRATEGY_EVALUATION`` carrying a
:class:`~backend.models.reassessment.ReassessmentRequest`: the trigger reason and
the hedge currently on the book (BRD §28).

:func:`build_reassessment_entry_state` builds that seed state;
:func:`build_reassessment_graph` compiles the sub-pipeline
``STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING`` from the *same*
node bodies the full graph uses (:func:`backend.agents.orchestrator.nodes.build_nodes`),
with the same ``NO_TRADE`` / ``REJECT`` short-circuits;
:func:`run_reassessment_cycle` runs it and returns the final state.

The seed state carries ``reassessment_origin=True`` so the ``MONITORING`` node at
the end of this sub-pipeline snapshots without escalating again — the loop closes
in one hop, it does not recurse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from backend.agents.monitoring.reassessment import (
    EscalationDecision,
    build_reassessment_request,
    should_escalate,
)
from backend.agents.orchestrator.graph import OrchestratorState
from backend.models.enums import WorkflowNode
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from backend.agents.orchestrator.nodes import OrchestratorDeps

__all__ = [
    "REASSESSMENT_ENTRY_NODE",
    "build_reassessment_entry_state",
    "build_reassessment_graph",
    "run_reassessment_cycle",
]

#: The node a reassessment cycle re-enters the graph at (task P7-BE-5).
REASSESSMENT_ENTRY_NODE: str = WorkflowNode.STRATEGY_EVALUATION.value

_STRATEGY = WorkflowNode.STRATEGY_EVALUATION.value
_RISK_CHECK = WorkflowNode.RISK_CHECK.value
_EXECUTION = WorkflowNode.EXECUTION.value
_MONITORING = WorkflowNode.MONITORING.value


def build_reassessment_entry_state(
    context: HedgeContext,
    monitoring_state: MonitoringState,
    *,
    escalation: EscalationDecision | None = None,
) -> OrchestratorState:
    """Seed state for a reassessment cycle that re-enters at ``STRATEGY_EVALUATION``.

    Carries the :class:`HedgeContext` (with the current hedge), the
    :class:`~backend.models.reassessment.ReassessmentRequest` (trigger reason +
    current hedge), and ``reassessment_origin=True`` so the terminal
    ``MONITORING`` node does not escalate a second time.
    """
    request = build_reassessment_request(
        context, monitoring_state, escalation=escalation
    )
    state: OrchestratorState = {
        "cycle_id": context.cycle_id,
        "hedge_context": context,
        "reassessment": request,
        "reassessment_origin": True,
        "notes": [
            f"REASSESSMENT: re-entering at {REASSESSMENT_ENTRY_NODE} — {request.reason}"
        ],
    }
    return state


def build_reassessment_graph(deps: "OrchestratorDeps") -> "CompiledStateGraph":
    """Compile ``STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING``.

    Reuses the real P6 node bodies; ``NO_TRADE`` / ``REASSESS`` skips the risk
    gate and ``REJECT`` skips the broker, exactly as in the full graph.
    """
    from backend.agents.orchestrator.nodes import (
        build_nodes,
        route_after_risk,
        route_after_strategy,
    )

    bodies = build_nodes(deps)
    graph: StateGraph = StateGraph(OrchestratorState)
    for name in (_STRATEGY, _RISK_CHECK, _EXECUTION, _MONITORING):
        graph.add_node(name, bodies[name])

    graph.add_edge(START, _STRATEGY)
    graph.add_conditional_edges(
        _STRATEGY,
        route_after_strategy,
        {_RISK_CHECK: _RISK_CHECK, _MONITORING: _MONITORING},
    )
    graph.add_conditional_edges(
        _RISK_CHECK,
        route_after_risk,
        {_EXECUTION: _EXECUTION, _MONITORING: _MONITORING},
    )
    graph.add_edge(_EXECUTION, _MONITORING)
    graph.add_edge(_MONITORING, END)
    return graph.compile()


def run_reassessment_cycle(
    deps: "OrchestratorDeps",
    context: HedgeContext,
    monitoring_state: MonitoringState,
    *,
    escalation: EscalationDecision | None = None,
) -> dict[str, Any]:
    """Escalate: build the entry state and run the reassessment sub-graph.

    Returns the final graph state (``visited`` starts at ``STRATEGY_EVALUATION``).
    """
    esc = escalation or should_escalate(monitoring_state)
    entry = build_reassessment_entry_state(context, monitoring_state, escalation=esc)
    graph = build_reassessment_graph(deps)
    return graph.invoke(entry)
