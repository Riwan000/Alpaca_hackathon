"""LangGraph state-machine for the autonomous hedge loop — tasks P6-BE-1…P6-BE-6.

Defines the six-node pipeline

    INITIAL → ANALYZING → STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING

as a :class:`langgraph.graph.StateGraph`.

P6-BE-1 built the *shape*: six placeholder bodies that only stamp ``current_node``
and append to ``visited``. P6-BE-2…P6-BE-6 (:mod:`backend.agents.orchestrator.nodes`)
supply the real agent chains — pass an :class:`~backend.agents.orchestrator.nodes.OrchestratorDeps`
to :func:`build_state_graph` / :func:`build_orchestrator_graph` and each node runs
its phase and writes its contract onto the state. With no ``deps`` the graph
keeps the placeholders, so the pure-shape checks (and a dependency-free
``invoke``) are unchanged.

The edges are still **linear**: ``NO_TRADE`` / ``REJECT`` / ``REASSESS``
short-circuits toward ``MONITORING`` are advisory (each decision node writes a
``route`` hint; :func:`~backend.agents.orchestrator.nodes.route_after_strategy`
and ``route_after_risk`` expose the same decision as pure functions) until
P6-BE-7 turns them into ``add_conditional_edges``.

The persisted-checkpoint / resume contract lives in
:mod:`backend.agents.orchestrator.runner` (task P6-DB-2) and is deliberately kept
separate from the graph definition here.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.models.enums import WorkflowNode
from backend.models.execution import ExecutionResult
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState
from backend.models.risk import RiskDecision
from backend.models.strategy import StrategyDecision

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from backend.agents.orchestrator.nodes import OrchestratorDeps

__all__ = [
    "GRAPH_NODES",
    "OrchestratorState",
    "build_state_graph",
    "build_orchestrator_graph",
    "render_mermaid",
]

#: The pipeline in execution order. ``COMPLETED`` / ``FAILED`` are terminal
#: markers on the persistence side (``workflow_state``), not graph nodes, so they
#: are not listed here.
GRAPH_NODES: tuple[str, ...] = (
    WorkflowNode.INITIAL.value,
    WorkflowNode.ANALYZING.value,
    WorkflowNode.STRATEGY_EVALUATION.value,
    WorkflowNode.RISK_CHECK.value,
    WorkflowNode.EXECUTION.value,
    WorkflowNode.MONITORING.value,
)


class OrchestratorState(TypedDict, total=False):
    """State threaded through the graph.

    ``total=False`` so a node returns only the keys it owns. ``visited``,
    ``errors`` and ``notes`` use an additive reducer so their trails survive the
    fan-in edges P6-BE-7 introduces; every other key is last-write-wins (only one
    node on any path owns it).

    ``degraded`` keeps its Phase 3 meaning — "some analysis sections are missing,
    continue anyway" (:data:`HedgeContext.degraded_sections`). A node that cannot
    run at all (no ``hedge_context`` in state, a hard failure) does **not** set
    ``degraded``; it appends to ``errors`` and routes to ``MONITORING``.
    ``notes`` collects advisory, non-error skips ("REJECT → execution skipped").

    The contract payloads (``hedge_context`` … ``monitoring_state``) are written
    by the P6-BE-2…P6-BE-6 nodes; a placeholder run never sets them. ``route`` is
    the advisory next-node hint a decision node leaves behind — read once by the
    P6-BE-7 branch functions, not a durable fact (see the module docstring).
    """

    cycle_id: str
    current_node: str
    visited: Annotated[list[str], operator.add]
    degraded: bool
    errors: Annotated[list[str], operator.add]
    notes: Annotated[list[str], operator.add]
    route: str
    hedge_context: HedgeContext
    strategy_decision: StrategyDecision
    risk_decision: RiskDecision
    execution_result: ExecutionResult
    monitoring_state: MonitoringState


def _placeholder(node: WorkflowNode) -> Any:
    """Build a no-op node body that records which node it ran as.

    Used when :func:`build_state_graph` is called with no ``deps``; P6-BE-2…P6-BE-6
    supply the real bodies. The return contract (a partial
    :class:`OrchestratorState`) is what the graph wiring depends on, not the body.
    """

    def _run(_state: OrchestratorState) -> dict[str, Any]:
        return {"current_node": node.value, "visited": [node.value]}

    _run.__name__ = f"{node.value.lower()}_node"
    _run.__qualname__ = _run.__name__
    _run.__doc__ = f"Placeholder body for the {node.value} node (P6-BE-1 skeleton)."
    return _run


def _node_bodies(deps: "OrchestratorDeps | None") -> dict[str, Any]:
    """The body for each pipeline node — placeholders when ``deps`` is ``None``.

    With ``deps`` the real P6-BE-2…P6-BE-6 chains are built by
    :func:`backend.agents.orchestrator.nodes.build_nodes` (imported lazily to keep
    the module import graph acyclic — ``nodes`` imports :class:`OrchestratorState`
    from here).
    """
    if deps is None:
        return {name: _placeholder(WorkflowNode(name)) for name in GRAPH_NODES}

    from backend.agents.orchestrator.nodes import build_nodes

    return build_nodes(deps)


def build_state_graph(deps: "OrchestratorDeps | None" = None) -> StateGraph:
    """The uncompiled :class:`StateGraph` builder — six nodes chained in order.

    ``deps=None`` wires the P6-BE-1 placeholders; an
    :class:`~backend.agents.orchestrator.nodes.OrchestratorDeps` wires the real
    phase chains. Returned uncompiled so P6-BE-7 can attach the conditional edges
    before calling :meth:`StateGraph.compile`.
    """
    graph = StateGraph(OrchestratorState)

    bodies = _node_bodies(deps)
    for name in GRAPH_NODES:
        graph.add_node(name, bodies[name])

    graph.add_edge(START, GRAPH_NODES[0])
    for src, dst in zip(GRAPH_NODES, GRAPH_NODES[1:]):
        graph.add_edge(src, dst)
    graph.add_edge(GRAPH_NODES[-1], END)

    return graph


def build_orchestrator_graph(
    deps: "OrchestratorDeps | None" = None,
) -> CompiledStateGraph:
    """Compile the pipeline into a runnable graph.

    With no ``deps`` a bare ``invoke({"cycle_id": ...})`` walks
    INITIAL → … → MONITORING over the placeholders and returns the state with
    ``visited == list(GRAPH_NODES)``. With ``deps`` each node runs its real phase.
    """
    return build_state_graph(deps).compile()


def render_mermaid() -> str:
    """Mermaid source for the compiled graph — the P6-BE-1 "render" confirm step.

    ``build_orchestrator_graph().get_graph().draw_mermaid()`` without the extra
    draw dependencies, so it is safe to call from a test or a REPL.
    """
    return build_orchestrator_graph().get_graph().draw_mermaid()


if __name__ == "__main__":  # pragma: no cover - manual "render the graph" check
    print(render_mermaid())
