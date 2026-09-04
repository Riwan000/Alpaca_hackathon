"""Orchestrator package — the autonomous hedge-assessment loop (Phase 6).

:mod:`backend.agents.orchestrator.runner` provides the resumable cycle runner
(task P6-DB-2): it drives the ``INITIAL → ANALYZING → STRATEGY_EVALUATION →
RISK_CHECK → EXECUTION → MONITORING`` pipeline, checkpointing every node
transition to ``workflow_state`` / ``workflow_transitions`` so a restart resumes
from the last persisted node instead of replaying the decision history.
"""

from __future__ import annotations

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
    "TERMINAL_NODE",
    "CycleContext",
    "CycleRunner",
    "NodeFn",
    "default_nodes",
    "run_cycle",
]
