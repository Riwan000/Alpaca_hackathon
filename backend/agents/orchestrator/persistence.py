"""State-persistence hook fired on every node transition — task P6-BE-10.

Wraps each graph node body so that **entering** and **leaving** it both write a
``workflow_state`` row (with a fresh ``updated_at``) and a ``workflow_transitions``
row. After a cycle runs, ``select current_node, updated_at from workflow_state``
shows every step it took, in order, and the transition log pairs an ``ENTER`` with
an ``EXIT`` for each node.

The sink is a :class:`TransitionSink` — :class:`WorkflowTransitionSink` persists
via :class:`~backend.db.workflow_repo.WorkflowRepository`; :class:`RecordingSink`
keeps the calls in memory for tests. Every write is best-effort: a persistence
error is logged, never raised, so the hook can never be the thing that breaks a
cycle (the same rule the terminal ``MONITORING`` node already follows).
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from backend.models.enums import WorkflowStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from backend.agents.orchestrator.graph import OrchestratorState
    from backend.agents.orchestrator.nodes import NodeBody

__all__ = [
    "TransitionPhase",
    "TransitionSink",
    "WorkflowTransitionSink",
    "RecordingSink",
    "with_transition_hook",
    "wrap_with_transition_hook",
]

logger = logging.getLogger(__name__)


class TransitionPhase(str, Enum):
    """Which edge of a node's execution a hook call marks."""

    ENTER = "ENTER"
    EXIT = "EXIT"


@runtime_checkable
class TransitionSink(Protocol):
    """Anything that can record a node entry/exit."""

    def record(
        self,
        cycle_id: str,
        node: str,
        phase: TransitionPhase,
        *,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None: ...


class WorkflowTransitionSink:
    """Persist every ENTER/EXIT to ``workflow_state`` / ``workflow_transitions``."""

    def __init__(self, engine: "Engine") -> None:
        from backend.db.workflow_repo import WorkflowRepository

        self._repo = WorkflowRepository(engine)

    def record(
        self,
        cycle_id: str,
        node: str,
        phase: TransitionPhase,
        *,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {
            "phase": phase.value,
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        if detail:
            merged.update(detail)
        try:
            self._repo.set_state(cycle_id, node, status, detail=merged)
        except Exception:  # noqa: BLE001 - a checkpoint write must never break the cycle
            logger.exception(
                "transition hook: could not persist %s %s for %s", node, phase.value, cycle_id
            )


@dataclass
class RecordingSink:
    """In-memory sink for tests — keeps the ordered call trail."""

    calls: list[tuple[str, str, TransitionPhase, str, dict[str, Any] | None]] = field(
        default_factory=list
    )

    def record(
        self,
        cycle_id: str,
        node: str,
        phase: TransitionPhase,
        *,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append((cycle_id, node, phase, status, detail))


def _exit_status(out: dict[str, Any]) -> str:
    """EXIT status: ``HALTED`` when the body flagged a critical failure, else ``RUNNING``."""
    if out.get("halted"):
        return WorkflowStatus.HALTED.value
    return WorkflowStatus.RUNNING.value


def with_transition_hook(
    node_name: str,
    body: "NodeBody",
    sink: TransitionSink,
) -> "NodeBody":
    """Return ``body`` wrapped so it records an ENTER before and an EXIT after."""

    def _run(state: "OrchestratorState") -> dict[str, Any]:
        cycle_id = str(state.get("cycle_id") or "unknown")
        sink.record(cycle_id, node_name, TransitionPhase.ENTER, status=WorkflowStatus.RUNNING.value)
        out = body(state)
        detail: dict[str, Any] = {}
        if isinstance(out, dict):
            if out.get("route"):
                detail["route"] = out["route"]
            if out.get("failure_class"):
                detail["failure_class"] = out["failure_class"]
        # the cycle id can be (re)written by a node (ANALYZING aligns it) — keep the trail on the live id
        exit_cycle_id = str(out.get("cycle_id") or cycle_id) if isinstance(out, dict) else cycle_id
        sink.record(
            exit_cycle_id,
            node_name,
            TransitionPhase.EXIT,
            status=_exit_status(out if isinstance(out, dict) else {}),
            detail=detail or None,
        )
        return out

    _run.__name__ = getattr(body, "__name__", node_name.lower())
    _run.__qualname__ = _run.__name__
    return _run


def wrap_with_transition_hook(
    bodies: dict[str, "NodeBody"],
    sink: TransitionSink | None,
) -> dict[str, "NodeBody"]:
    """Wrap every body in ``bodies`` with the hook; a ``None`` sink is a pass-through."""
    if sink is None:
        return bodies
    return {name: with_transition_hook(name, body, sink) for name, body in bodies.items()}


#: A node body wrapper — kept as a type alias hint for callers building their own.
NodeWrapper = Callable[[str, "NodeBody", TransitionSink], "NodeBody"]
