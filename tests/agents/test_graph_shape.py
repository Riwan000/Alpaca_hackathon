"""LangGraph orchestrator skeleton — graph-shape checks — task P6-BE-1 / issue #147.

Confirms:
- the graph **compiles**;
- its nodes are exactly the six-node pipeline, in the order the BRD names them;
- its **edges match the linear spec** — ``START → INITIAL → … → MONITORING → END``
  with no extra or missing edge, and no conditional branching yet (that is
  P6-BE-7);
- **no unreachable node** — every node is reachable from ``START`` and every node
  can still reach ``END``;
- a bare invocation walks the six nodes once, in order (the "render the graph;
  the six nodes chain in order" confirm step).
"""

from __future__ import annotations

import pytest

from backend.agents.orchestrator.graph import (
    GRAPH_NODES,
    build_orchestrator_graph,
    build_state_graph,
    render_mermaid,
)
from backend.models.enums import WorkflowNode

pytestmark = pytest.mark.unit

_START = "__start__"
_END = "__end__"

#: The pipeline exactly as the BRD / issue #147 spells it.
_EXPECTED_NODES: tuple[str, ...] = (
    "INITIAL",
    "ANALYZING",
    "STRATEGY_EVALUATION",
    "RISK_CHECK",
    "EXECUTION",
    "MONITORING",
)


def _edge_set(compiled) -> set[tuple[str, str]]:
    return {(edge.source, edge.target) for edge in compiled.get_graph().edges}


def _node_names(compiled) -> list[str]:
    return [name for name in compiled.get_graph().nodes if name not in (_START, _END)]


def test_node_order_matches_the_spec() -> None:
    assert GRAPH_NODES == _EXPECTED_NODES
    # …and each name is a real WorkflowNode member (no typo drift).
    assert [WorkflowNode(n) for n in GRAPH_NODES] == [
        WorkflowNode.INITIAL,
        WorkflowNode.ANALYZING,
        WorkflowNode.STRATEGY_EVALUATION,
        WorkflowNode.RISK_CHECK,
        WorkflowNode.EXECUTION,
        WorkflowNode.MONITORING,
    ]


def test_graph_compiles() -> None:
    compiled = build_orchestrator_graph()
    assert compiled is not None
    # compiling twice yields an independent, equivalent graph
    assert _node_names(compiled) == _node_names(build_orchestrator_graph())


def test_nodes_are_exactly_the_six_pipeline_nodes() -> None:
    compiled = build_orchestrator_graph()
    assert _node_names(compiled) == list(GRAPH_NODES)


def test_edges_match_the_linear_spec() -> None:
    compiled = build_orchestrator_graph()

    expected = {(_START, GRAPH_NODES[0]), (GRAPH_NODES[-1], _END)}
    expected |= set(zip(GRAPH_NODES, GRAPH_NODES[1:]))

    assert _edge_set(compiled) == expected


def test_no_conditional_branching_yet() -> None:
    # P6-BE-1 is the plain chain; NO_TRADE / REJECT / REASSESS routing is P6-BE-7.
    builder = build_state_graph()
    assert builder.branches == {}


def test_every_node_is_reachable_from_start_and_reaches_end() -> None:
    compiled = build_orchestrator_graph()
    edges = _edge_set(compiled)
    nodes = {*_node_names(compiled), _START, _END}

    forward: dict[str, set[str]] = {n: set() for n in nodes}
    backward: dict[str, set[str]] = {n: set() for n in nodes}
    for src, dst in edges:
        forward[src].add(dst)
        backward[dst].add(src)

    def _closure(adj: dict[str, set[str]], root: str) -> set[str]:
        seen: set[str] = set()
        stack = [root]
        while stack:
            cur = stack.pop()
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    reachable_from_start = _closure(forward, _START)
    can_reach_end = _closure(backward, _END)

    for node in GRAPH_NODES:
        assert node in reachable_from_start, f"{node} unreachable from START"
        assert node in can_reach_end, f"{node} cannot reach END"


def test_invocation_walks_the_six_nodes_in_order() -> None:
    compiled = build_orchestrator_graph()
    final = compiled.invoke({"cycle_id": "cyc_shape_test"})

    assert final["cycle_id"] == "cyc_shape_test"
    assert final["visited"] == list(GRAPH_NODES)
    assert final["current_node"] == WorkflowNode.MONITORING.value


def test_render_mermaid_lists_the_six_nodes_in_order() -> None:
    mermaid = render_mermaid()

    positions = [mermaid.find(node) for node in GRAPH_NODES]
    assert all(pos != -1 for pos in positions), "a node is missing from the render"
    assert positions == sorted(positions), "nodes are not rendered in pipeline order"
