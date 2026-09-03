"""Workflow state & transitions repository — task P6-DB-1, P6-DB-2.

Persists LangGraph state machine node transitions and current workflow status
per cycle. Allows resuming execution upon restart and reading the full transition
history.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from typing import Any

from sqlalchemy import MetaData, Table, desc, insert, select, update
from sqlalchemy.engine import Engine

from backend.models.enums import WorkflowNode, WorkflowStatus

_STATE_TABLE = "workflow_state"
_TRANSITIONS_TABLE = "workflow_transitions"


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
        self._state_table = Table(_STATE_TABLE, MetaData(), autoload_with=engine)
        self._transitions_table = Table(_TRANSITIONS_TABLE, MetaData(), autoload_with=engine)

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
