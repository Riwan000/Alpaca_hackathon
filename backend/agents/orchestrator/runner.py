"""Resumable orchestrator cycle runner — task P6-DB-2.

Wires the six workflow nodes

    INITIAL → ANALYZING → STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING

into one sequential pass whose progress is **checkpointed to the database after
every node** (:class:`backend.db.workflow_repo.WorkflowRepository`). Because the
last completed node is persisted, a process that is killed mid-cycle — Ctrl-C
during ``ANALYZING``, a crash, a redeploy — can be restarted and *resumes from
the node after the last one that finished* instead of replaying the whole
decision history (Tech-Stack §21). A node that checkpointed is skipped on
resume; a node killed *inside its body* (before its checkpoint) is re-entered.

The node bodies here are thin placeholders; the Phase 6 backend tasks
(P6-BE-2 … P6-BE-6) swap each one for the real agent chain. The runner keeps the
checkpoint / resume contract stable regardless of what a node does. The one
obligation on a node body: if it has an external side effect (``EXECUTION``
submitting an order) it must be **idempotent**, guarding on its *own* persisted
effect — ``OrderRepository.list_for_cycle(ctx.cycle_id)`` — because a kill inside
the body re-runs it. :meth:`CycleContext.already_ran` does not serve that purpose
(it only reports nodes *upstream* of the caller).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import Engine

from backend.db.workflow_repo import WorkflowRepository, WorkflowStateRecord
from backend.models.enums import WorkflowNode, WorkflowStatus

__all__ = [
    "CYCLE_NODES",
    "TERMINAL_NODE",
    "CycleContext",
    "NodeFn",
    "CycleRunner",
    "default_nodes",
    "run_cycle",
]

#: The pipeline, in execution order. ``COMPLETED`` / ``FAILED`` are terminal
#: markers rather than steps, so they are not listed here.
CYCLE_NODES: tuple[str, ...] = (
    WorkflowNode.INITIAL.value,
    WorkflowNode.ANALYZING.value,
    WorkflowNode.STRATEGY_EVALUATION.value,
    WorkflowNode.RISK_CHECK.value,
    WorkflowNode.EXECUTION.value,
    WorkflowNode.MONITORING.value,
)

#: State a finished cycle lands in.
TERMINAL_NODE: str = WorkflowNode.COMPLETED.value

_TERMINAL_NODES: frozenset[str] = frozenset(
    {WorkflowNode.COMPLETED.value, WorkflowNode.FAILED.value}
)
#: A cycle whose latest state carries one of these as its ``status`` is finished
#: — ``run`` returns it untouched rather than resuming or re-completing it.
#: ``RUNNING`` / ``PENDING`` / ``HALTED`` all resume.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {WorkflowStatus.COMPLETED.value, WorkflowStatus.FAILED.value}
)


@dataclass
class CycleContext:
    """Mutable scratch handed to every node body during one process's run.

    ``completed_nodes`` holds the pipeline nodes *upstream* of the one now
    running — the ones a previous process checkpointed before a restart, plus the
    ones this process has finished so far. It is populated only up to (never
    including) the current node, so :meth:`already_ran` is a way for a *later*
    node to gate on an *earlier* one; it is **never** true for the node that is
    executing and so cannot be a node's own idempotency guard. A node with an
    external side effect (``EXECUTION``) must instead check the persisted effect
    itself — e.g. ``OrderRepository.list_for_cycle(ctx.cycle_id)`` — because a
    kill inside the body, before its checkpoint, re-enters it on resume.

    ``scratch`` is shared in-memory state between nodes within a single process;
    it does **not** survive a restart (only the DB checkpoint does), so a
    resuming node must rebuild what it needs from persisted rows.
    """

    cycle_id: str
    engine: Engine
    completed_nodes: list[str] = field(default_factory=list)
    scratch: dict[str, Any] = field(default_factory=dict)

    def already_ran(self, node: str | WorkflowNode) -> bool:
        """True if ``node`` — an *upstream* node — has been checkpointed already.

        Only meaningful for a node asking about one earlier in the pipeline; it
        never reports the currently-running node as done (see the class
        docstring).
        """
        value = node.value if isinstance(node, WorkflowNode) else str(node)
        return value in self.completed_nodes


#: A node body: given the cycle context, do the work and return an optional
#: JSON-serialisable ``detail`` dict to persist alongside the checkpoint.
NodeFn = Callable[[CycleContext], "dict[str, Any] | None"]


def _noop(_ctx: CycleContext) -> None:
    return None


def default_nodes() -> dict[str, NodeFn]:
    """Placeholder node bodies — one no-op per pipeline node.

    Phase 6 backend tasks replace these with the real chains; the runner does
    not care what a node does as long as it returns ``None`` or a ``detail``
    dict.
    """
    return {node: _noop for node in CYCLE_NODES}


def _mint_cycle_id() -> str:
    return f"cyc_{uuid.uuid4().hex[:8]}"


def _resume_index(state: WorkflowStateRecord | None) -> int:
    """Index into :data:`CYCLE_NODES` of the next node to run.

    ``None`` state → ``0`` (fresh start). A persisted non-terminal node → the
    slot right after it (resume). A terminal or unrecognised node → past the end
    (nothing left to run).
    """
    if state is None:
        return 0
    if state.current_node in _TERMINAL_NODES:
        return len(CYCLE_NODES)
    try:
        return CYCLE_NODES.index(state.current_node) + 1
    except ValueError:
        return 0


class CycleRunner:
    """Runs the workflow pipeline, checkpointing after each node so it can resume."""

    def __init__(
        self,
        engine: Engine,
        nodes: Mapping[str, NodeFn] | None = None,
    ) -> None:
        self._engine = engine
        resolved = default_nodes()
        if nodes:
            unknown = sorted(set(nodes) - set(CYCLE_NODES))
            if unknown:
                raise ValueError(
                    f"unknown node name(s) {unknown}; expected a subset of "
                    f"{list(CYCLE_NODES)} — a typo here would silently leave the "
                    "real node as a no-op"
                )
            resolved.update(nodes)
        self._nodes: dict[str, NodeFn] = resolved

    def run(
        self,
        cycle_id: str | None = None,
        *,
        resume: bool = True,
    ) -> WorkflowStateRecord:
        """Execute (or resume) the cycle and return its final ``workflow_state`` row.

        ``cycle_id=None`` with ``resume=True`` picks up the most recent
        unfinished cycle if there is one, otherwise starts a fresh cycle. A cycle
        already terminal — ``COMPLETED`` or ``FAILED`` — is returned untouched,
        so calling ``run`` again is a safe no-op. On ``KeyboardInterrupt`` /
        ``SystemExit`` the last completed node (or ``INITIAL`` for a brand-new
        cycle interrupted before any node finished) is recorded as ``HALTED`` and
        the exception re-raised, so the cycle stays discoverable and the next
        ``run`` resumes from the following node.

        A node body with an external side effect (``EXECUTION``) must be
        idempotent: a kill *inside* the body, before its checkpoint, re-enters it
        on resume. Such a node must check its own persisted effect — e.g.
        ``OrderRepository.list_for_cycle(ctx.cycle_id)`` — before acting.
        :meth:`CycleContext.already_ran` does **not** help here: it only ever
        reports *upstream* nodes, never the one currently running.
        """
        repo = WorkflowRepository(self._engine)

        if cycle_id is None:
            cycle_id = (
                repo.latest_unfinished_cycle() if resume else None
            ) or _mint_cycle_id()

        existing = repo.get_state(cycle_id) if resume else None
        if existing is not None and (
            existing.current_node in _TERMINAL_NODES
            or existing.status in _TERMINAL_STATUSES
        ):
            # Already finished (COMPLETED) or deliberately terminal (FAILED) —
            # never silently re-run or force-complete it.
            return existing

        start = _resume_index(existing) if resume else 0
        ctx = CycleContext(
            cycle_id=cycle_id,
            engine=self._engine,
            completed_nodes=list(CYCLE_NODES[:start]),
        )

        try:
            for node in CYCLE_NODES[start:]:
                detail = self._nodes[node](ctx) or None
                repo.set_state(cycle_id, node, WorkflowStatus.RUNNING, detail=detail)
                ctx.completed_nodes.append(node)
            return repo.set_state(cycle_id, TERMINAL_NODE, WorkflowStatus.COMPLETED)
        except (KeyboardInterrupt, SystemExit):
            # Record where we stopped so the cycle is never orphaned. For a
            # brand-new cycle killed before its first node finished there is no
            # completed node yet — checkpoint INITIAL so a cold restart can still
            # find and resume it (resume then continues at ANALYZING).
            halted_at = ctx.completed_nodes[-1] if ctx.completed_nodes else CYCLE_NODES[0]
            repo.set_state(
                cycle_id,
                halted_at,
                WorkflowStatus.HALTED,
                detail={"halted": True, "reason": "interrupted"},
            )
            raise


def run_cycle(
    engine: Engine,
    cycle_id: str | None = None,
    *,
    nodes: Mapping[str, NodeFn] | None = None,
    resume: bool = True,
) -> WorkflowStateRecord:
    """One-call helper: build a :class:`CycleRunner` and run (or resume) a cycle."""
    return CycleRunner(engine, nodes=nodes).run(cycle_id, resume=resume)
