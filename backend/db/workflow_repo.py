"""Workflow state & transitions repository — task P6-DB-1, P6-DB-2.

Persists LangGraph state machine node transitions and current workflow status
per cycle. Allows resuming execution upon restart and reading the full transition
history.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from typing import Any

from sqlalchemy import desc, func, insert, select
from sqlalchemy.engine import Engine

from backend.db.table_cache import get_table
from backend.models.enums import WorkflowNode, WorkflowStatus

_STATE_TABLE = "workflow_state"
_TRANSITIONS_TABLE = "workflow_transitions"

#: A cycle whose latest state carries one of these — either as its ``status`` or
#: as its ``current_node`` — is finished and never resumed.
_TERMINAL_STATUSES = ("COMPLETED", "FAILED")
_TERMINAL_NODES = ("COMPLETED", "FAILED")


@dataclasses.dataclass(frozen=True)
class WorkflowStateRecord:
    """One ``workflow_state`` row."""

    cycle_id: str
    current_node: str
    status: str
    detail: dict[str, Any] | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class WorkflowTransitionRecord:
    """One ``workflow_transitions`` row."""

    cycle_id: str
    from_node: str | None
    to_node: str
    status: str
    detail: dict[str, Any] | None = None
    transitioned_at: _dt.datetime | None = None
    id: int | None = None


class WorkflowRepository:
    """CRUD access for workflow states and transition logs."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._state_table = get_table(engine, _STATE_TABLE)
        self._transitions_table = get_table(engine, _TRANSITIONS_TABLE)

    def set_state(
        self,
        cycle_id: str,
        current_node: str | WorkflowNode,
        status: str | WorkflowStatus,
        detail: dict[str, Any] | None = None,
    ) -> WorkflowStateRecord:
        """Create or update current state for a cycle, and record a transition."""
        node_str = current_node.value if isinstance(current_node, WorkflowNode) else str(current_node)
        status_str = status.value if isinstance(status, WorkflowStatus) else str(status)
        now = _dt.datetime.now(_dt.timezone.utc)

        with self._engine.begin() as conn:
            # Check existing state
            existing = conn.execute(
                select(self._state_table)
                .where(self._state_table.c.cycle_id == cycle_id)
                .order_by(desc(self._state_table.c.id))
                .limit(1)
            ).mappings().first()

            from_node = existing["current_node"] if existing else None

            # Insert new state row or update
            result = conn.execute(
                insert(self._state_table).values(
                    cycle_id=cycle_id,
                    current_node=node_str,
                    status=status_str,
                    detail=detail,
                    created_at=now,
                    updated_at=now,
                )
            )
            state_id = int(result.inserted_primary_key[0])

            # Record transition log
            conn.execute(
                insert(self._transitions_table).values(
                    cycle_id=cycle_id,
                    from_node=from_node,
                    to_node=node_str,
                    status=status_str,
                    detail=detail,
                    transitioned_at=now,
                )
            )

        return WorkflowStateRecord(
            id=state_id,
            cycle_id=cycle_id,
            current_node=node_str,
            status=status_str,
            detail=detail,
            created_at=now,
            updated_at=now,
        )

    def get_state(self, cycle_id: str) -> WorkflowStateRecord | None:
        """Fetch the latest workflow state for ``cycle_id``."""
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._state_table)
                .where(self._state_table.c.cycle_id == cycle_id)
                .order_by(desc(self._state_table.c.id))
                .limit(1)
            ).mappings().first()

        if not row:
            return None

        return WorkflowStateRecord(
            id=row["id"],
            cycle_id=row["cycle_id"],
            current_node=row["current_node"],
            status=row["status"],
            detail=row["detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def latest_unfinished_cycle(self) -> str | None:
        """Return the ``cycle_id`` of the most recently touched cycle that has
        not finished, or ``None`` if every cycle is terminal.

        Used on a cold start to answer "was a cycle interrupted — should I resume
        it rather than begin a new one?". A cycle counts as unfinished when its
        latest ``workflow_state`` row is neither ``COMPLETED`` nor ``FAILED`` (by
        status or node); ``RUNNING``, ``PENDING`` and ``HALTED`` all resume.
        """
        latest_ids = (
            select(func.max(self._state_table.c.id).label("mid"))
            .group_by(self._state_table.c.cycle_id)
            .subquery()
        )
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(self._state_table)
                    .join(latest_ids, self._state_table.c.id == latest_ids.c.mid)
                    .where(self._state_table.c.status.notin_(_TERMINAL_STATUSES))
                    .where(self._state_table.c.current_node.notin_(_TERMINAL_NODES))
                    .order_by(desc(self._state_table.c.id))
                    .limit(1)
                )
                .mappings()
                .first()
            )
        return row["cycle_id"] if row else None

    def get_transitions(self, cycle_id: str) -> list[WorkflowTransitionRecord]:
        """Fetch transition history for ``cycle_id`` in chronological order."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._transitions_table)
                .where(self._transitions_table.c.cycle_id == cycle_id)
                .order_by(self._transitions_table.c.id.asc())
            ).mappings().all()

        return [
            WorkflowTransitionRecord(
                id=r["id"],
                cycle_id=r["cycle_id"],
                from_node=r["from_node"],
                to_node=r["to_node"],
                status=r["status"],
                detail=r["detail"],
                transitioned_at=r["transitioned_at"],
            )
            for r in rows
        ]
