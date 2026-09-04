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

Routing (task P6-BE-7): when :func:`build_state_graph` is given ``deps`` the
decision points become ``add_conditional_edges`` — ``ANALYZING`` skips straight
to ``MONITORING`` on a hard/critical failure, ``STRATEGY_EVALUATION`` skips the
risk gate on ``NO_TRADE`` / ``REASSESS``, and ``RISK_CHECK`` skips the broker on
``REJECT`` (or any non-``APPROVE``/``MODIFY`` verdict). The branch targets are the
pure functions :func:`~backend.agents.orchestrator.nodes.route_after_analyzing`,
``route_after_strategy`` and ``route_after_risk``. The dependency-free skeleton
(``deps=None``) keeps the plain linear chain so the P6-BE-1 shape checks — and a
bare ``invoke`` over the placeholders — are unchanged.

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
from backend.models.reassessment import ReassessmentDecision, ReassessmentRequest
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

    ``halted`` / ``failure_class`` are set by a node whose caught failure the
    P6-BE-9 classifier judged ``CRITICAL`` (BRD §31 — "do not trade"): the node
    also sets ``route=MONITORING`` so the cycle short-circuits to the terminal
    node without touching the broker, and the persistence hook records the exit
    as ``HALTED`` rather than ``RUNNING``.

    The contract payloads (``hedge_context`` … ``monitoring_state``) are written
    by the P6-BE-2…P6-BE-6 nodes; a placeholder run never sets them. ``route`` is
    the next-node hint a decision node leaves behind; with ``deps`` wired it is
    also what the P6-BE-7 conditional edges act on (via the pure ``route_after_*``
    functions, which re-derive it from the decision rather than trusting the hint).
    """

    cycle_id: str
    current_node: str
    visited: Annotated[list[str], operator.add]
    degraded: bool
    errors: Annotated[list[str], operator.add]
    notes: Annotated[list[str], operator.add]
    route: str
    halted: bool
    failure_class: str
    hedge_context: HedgeContext
    strategy_decision: StrategyDecision
    risk_decision: RiskDecision
    execution_result: ExecutionResult
    monitoring_state: MonitoringState
    # Phase 7 — Level-2 reassessment (P7-BE-5 / P7-BE-8). ``reassessment`` is the
    # trigger payload a fired Level-1 check carries into a reassessment cycle;
    # ``reassessment_origin`` marks a state that is *already* a Level-2 cycle so
    # ``MONITORING`` snapshots without escalating again (no loop);
    # ``reassessment_decision`` / ``reassessment_result`` are what the escalation
    # writes back.
    reassessment: ReassessmentRequest
    reassessment_origin: bool
    reassessment_decision: ReassessmentDecision
    reassessment_result: "dict[str, Any]"


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
    """The uncompiled :class:`StateGraph` builder.

    ``deps=None`` wires the P6-BE-1 placeholders in a plain linear chain. An
    :class:`~backend.agents.orchestrator.nodes.OrchestratorDeps` wires the real
    phase chains **and** the P6-BE-7 conditional edges at ``ANALYZING`` /
    ``STRATEGY_EVALUATION`` / ``RISK_CHECK``. Returned uncompiled so a caller can
    still inspect ``.branches`` / attach a checkpointer before
    :meth:`StateGraph.compile`.
    """
    graph = StateGraph(OrchestratorState)

    bodies = _node_bodies(deps)
    for name in GRAPH_NODES:
        graph.add_node(name, bodies[name])

    graph.add_edge(START, GRAPH_NODES[0])

    if deps is None:
        for src, dst in zip(GRAPH_NODES, GRAPH_NODES[1:]):
            graph.add_edge(src, dst)
        graph.add_edge(GRAPH_NODES[-1], END)
        return graph

    _wire_conditional_edges(graph)
    return graph


def _wire_conditional_edges(graph: StateGraph) -> None:
    """Attach the P6-BE-7 routing — decision points fan out, the rest stays linear.

    ``INITIAL → ANALYZING`` and ``EXECUTION → MONITORING → END`` are unconditional;
    the three decision nodes route through the pure ``route_after_*`` functions so
    a ``NO_TRADE`` / ``REASSESS`` / ``REJECT`` (or a critical failure upstream)
    skips every node it should and lands on ``MONITORING``.
    """
    from backend.agents.orchestrator.nodes import (
        route_after_analyzing,
        route_after_risk,
        route_after_strategy,
    )

    initial, analyzing, strategy, risk, execution, monitoring = GRAPH_NODES

    graph.add_edge(initial, analyzing)
    graph.add_conditional_edges(
        analyzing,
        route_after_analyzing,
        {strategy: strategy, monitoring: monitoring},
    )
    graph.add_conditional_edges(
        strategy,
        route_after_strategy,
        {risk: risk, monitoring: monitoring},
    )
    graph.add_conditional_edges(
        risk,
        route_after_risk,
        {execution: execution, monitoring: monitoring},
    )
    graph.add_edge(execution, monitoring)
    graph.add_edge(monitoring, END)


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
