"""LangGraph state-machine skeleton for the autonomous hedge loop — task P6-BE-1.

Defines the six-node pipeline

    INITIAL → ANALYZING → STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING

as a :class:`langgraph.graph.StateGraph`. This task is the *shape* only: every
node body is a thin placeholder that stamps ``current_node`` onto the state and
appends itself to ``visited``. Phase-6 backend tasks P6-BE-2…P6-BE-6 swap each
placeholder for the real agent chain, and P6-BE-7 adds the conditional edges
(``NO_TRADE`` / ``REJECT`` / ``REASSESS`` short-circuits toward ``MONITORING``).
Until then the nodes chain unconditionally in order, so a compiled run visits all
six exactly once.

The persisted-checkpoint / resume contract lives in
:mod:`backend.agents.orchestrator.runner` (task P6-DB-2) and is deliberately kept
separate from the graph definition here.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.models.enums import WorkflowNode

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

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

    Skeleton shape — the analysis / strategy / risk / execution payload keys are
    added by P6-BE-2…P6-BE-6 as each node starts producing a real contract.
    ``total=False`` so a node returns only the keys it owns; ``visited`` uses an
    additive reducer so the trail survives the fan-in edges P6-BE-7 introduces.
    """

    cycle_id: str
    current_node: str
    visited: Annotated[list[str], operator.add]
    degraded: bool


def _placeholder(node: WorkflowNode) -> Any:
    """Build a no-op node body that records which node it ran as.

    Replaced wholesale by P6-BE-2…P6-BE-6; the return contract (a partial
    :class:`OrchestratorState`) is what the graph wiring depends on, not the
    body.
    """

    def _run(_state: OrchestratorState) -> dict[str, Any]:
        return {"current_node": node.value, "visited": [node.value]}

    _run.__name__ = f"{node.value.lower()}_node"
    _run.__qualname__ = _run.__name__
    _run.__doc__ = f"Placeholder body for the {node.value} node (P6-BE-1 skeleton)."
    return _run


def build_state_graph() -> StateGraph:
    """The uncompiled :class:`StateGraph` builder — six nodes chained in order.

    Returned uncompiled so later tasks can attach real bodies and the
    conditional edges (P6-BE-7) before calling :meth:`StateGraph.compile`.
    """
    graph = StateGraph(OrchestratorState)

    for name in GRAPH_NODES:
        graph.add_node(name, _placeholder(WorkflowNode(name)))

    graph.add_edge(START, GRAPH_NODES[0])
    for src, dst in zip(GRAPH_NODES, GRAPH_NODES[1:]):
        graph.add_edge(src, dst)
    graph.add_edge(GRAPH_NODES[-1], END)

    return graph


def build_orchestrator_graph() -> CompiledStateGraph:
    """Compile the skeleton into a runnable graph.

    A bare ``invoke({"cycle_id": ...})`` walks INITIAL → … → MONITORING and
    returns the state with ``visited == list(GRAPH_NODES)``.
    """
    return build_state_graph().compile()


def render_mermaid() -> str:
    """Mermaid source for the compiled graph — the P6-BE-1 "render" confirm step.

    ``build_orchestrator_graph().get_graph().draw_mermaid()`` without the extra
    draw dependencies, so it is safe to call from a test or a REPL.
    """
    return build_orchestrator_graph().get_graph().draw_mermaid()


if __name__ == "__main__":  # pragma: no cover - manual "render the graph" check
    print(render_mermaid())
