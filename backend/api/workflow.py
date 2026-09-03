"""Workflow state read-back endpoint — task P6-DB-3.

Provides `GET /cycle/{cycle_id}/state` returning current workflow node, status,
and transition history.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.workflow_repo import WorkflowRepository

router = APIRouter(tags=["workflow"])


class WorkflowTransitionOut(BaseModel):
    id: int | None = None
    from_node: str | None = None
    to_node: str
    status: str
    detail: dict[str, Any] | None = None
    transitioned_at: _dt.datetime | None = None


class CycleStateOut(BaseModel):
    cycle_id: str
    current_node: str
    status: str
    detail: dict[str, Any] | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    transitions: list[WorkflowTransitionOut] = []


@router.get("/cycle/{cycle_id}/state", response_model=CycleStateOut)
def get_cycle_state(
    cycle_id: str = Path(..., description="Unique ID of the orchestrator run cycle"),
    engine: Engine = Depends(get_readback_engine),
) -> CycleStateOut:
    """Return current node, status, and transition history for a cycle."""
    repo = WorkflowRepository(engine)
    state = repo.get_state(cycle_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"No workflow state found for cycle_id '{cycle_id}'",
        )

    transitions = repo.get_transitions(cycle_id)
    return CycleStateOut(
        cycle_id=state.cycle_id,
        current_node=state.current_node,
        status=state.status,
        detail=state.detail,
        created_at=state.created_at,
        updated_at=state.updated_at,
        transitions=[
            WorkflowTransitionOut(
                id=t.id,
                from_node=t.from_node,
                to_node=t.to_node,
                status=t.status,
                detail=t.detail,
                transitioned_at=t.transitioned_at,
            )
            for t in transitions
        ],
    )
