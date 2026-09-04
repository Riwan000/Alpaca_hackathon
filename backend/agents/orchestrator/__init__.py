"""Orchestrator package — the autonomous hedge-assessment loop (Phase 6).

:mod:`backend.agents.orchestrator.graph` defines the LangGraph state machine
(``INITIAL → ANALYZING → STRATEGY_EVALUATION → RISK_CHECK → EXECUTION →
MONITORING``). :mod:`backend.agents.orchestrator.nodes` (tasks P6-BE-2…P6-BE-6)
supplies the real node bodies wrapping Phases 3–5; pass an
:class:`~backend.agents.orchestrator.nodes.OrchestratorDeps` to
:func:`~backend.agents.orchestrator.graph.build_orchestrator_graph` to wire them.

:mod:`backend.agents.orchestrator.runner` provides the resumable cycle runner
(task P6-DB-2): it drives the same pipeline, checkpointing every node transition
to ``workflow_state`` / ``workflow_transitions`` so a restart resumes from the
last persisted node instead of replaying the decision history.
"""

from __future__ import annotations

from backend.agents.orchestrator.graph import (
    GRAPH_NODES,
    OrchestratorState,
    build_orchestrator_graph,
    build_state_graph,
    render_mermaid,
)
from backend.agents.orchestrator.nodes import (
    NodeBody,
    OrchestratorDeps,
    build_nodes,
    route_after_analyzing,
    route_after_risk,
    route_after_strategy,
)
from backend.agents.orchestrator.persistence import (
    RecordingSink,
    TransitionPhase,
    TransitionSink,
    WorkflowTransitionSink,
    with_transition_hook,
    wrap_with_transition_hook,
)
from backend.agents.orchestrator.resilience import (
    CriticalFailure,
    FailureClass,
    RecoverableFailure,
    RetriesExhausted,
    RetryPolicy,
    TransientError,
    classify_failure,
    is_transient,
    run_with_retry,
)
from backend.agents.orchestrator.runner import (
    CYCLE_NODES,
    TERMINAL_NODE,
    CycleContext,
    CycleRunner,
    NodeFn,
    default_nodes,
    run_cycle,
)

__all__ = [
    "CYCLE_NODES",
    "GRAPH_NODES",
    "TERMINAL_NODE",
    "CriticalFailure",
    "CycleContext",
    "CycleRunner",
    "FailureClass",
    "NodeBody",
    "NodeFn",
    "OrchestratorDeps",
    "OrchestratorState",
    "RecordingSink",
    "RecoverableFailure",
    "RetriesExhausted",
    "RetryPolicy",
    "TransientError",
    "TransitionPhase",
    "TransitionSink",
    "WorkflowTransitionSink",
    "build_nodes",
    "build_orchestrator_graph",
    "build_state_graph",
    "classify_failure",
    "default_nodes",
    "is_transient",
    "render_mermaid",
    "route_after_analyzing",
    "route_after_risk",
    "route_after_strategy",
    "run_cycle",
    "run_with_retry",
    "with_transition_hook",
    "wrap_with_transition_hook",
]
