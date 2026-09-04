"""Workflow endpoints — tasks P6-DB-3, P6-BE-11, P6-BE-12.

* ``GET /cycle/{cycle_id}/state`` — full state + transition history (P6-DB-3).
* ``POST /run-cycle``            — trigger the orchestrator graph (P6-BE-11 / #157).
* ``GET /workflow-state``        — latest state for a cycle or the most-recent
  active cycle (P6-BE-12 / #158).
* ``GET /workflow-state/stream`` — SSE stream that emits one event per new
  ``workflow_transitions`` row; closes when the cycle completes (P6-BE-12 / #158).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import get_readback_engine
from backend.db.workflow_repo import WorkflowRepository

router = APIRouter(tags=["workflow"])


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# P6-DB-3 - GET /cycle/{cycle_id}/state
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# P6-BE-11 - POST /run-cycle  (#157)
# ---------------------------------------------------------------------------


class RunCycleIn(BaseModel):
    force: bool = False


class RunCycleOut(BaseModel):
    cycle_id: str
    status: str
    message: str
    started_at: _dt.datetime


def get_orchestrator_deps() -> Any:  # pragma: no cover
    """FastAPI dependency - returns a live OrchestratorDeps; overridden in tests."""
    from backend.agents.orchestrator.nodes import OrchestratorDeps
    return OrchestratorDeps()


@router.post("/run-cycle", response_model=RunCycleOut, status_code=202)
def trigger_run_cycle(
    payload: RunCycleIn = RunCycleIn(),
    engine: Engine = Depends(get_readback_engine),
    deps: Any = Depends(get_orchestrator_deps),
) -> RunCycleOut:
    """Trigger an autonomous hedge assessment cycle (P6-BE-11 / #157).

    Starts the six-node LangGraph pipeline in a background thread and returns
    202 Accepted immediately with the new cycle_id.  Progress is readable via
    GET /cycle/{cycle_id}/state or GET /workflow-state/stream?cycle_id=...
    """
    import dataclasses
    import threading
    import uuid

    from backend.agents.orchestrator.graph import build_orchestrator_graph
    from backend.agents.orchestrator.nodes import OrchestratorDeps
    from backend.db.workflow_repo import WorkflowRepository as _WFRepo

    cycle_id = "cyc_" + uuid.uuid4().hex[:8]
    now = _dt.datetime.now(_dt.timezone.utc)

    # Stamp INITIAL immediately so callers can find the cycle before the
    # background thread begins its first real node.
    try:
        _WFRepo(engine).set_state(cycle_id, "INITIAL", "RUNNING")
    except Exception:  # noqa: BLE001
        pass  # cold-start / unmigrated DB

    # Ensure the deps have a DB engine for transition persistence.
    if isinstance(deps, OrchestratorDeps):
        wired: OrchestratorDeps = deps
        if wired.engine is None:
            wired = dataclasses.replace(wired, engine=engine)
    else:
        wired = OrchestratorDeps(engine=engine)

    graph = build_orchestrator_graph(wired)

    def _run() -> None:
        try:
            graph.invoke({"cycle_id": cycle_id})
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "run-cycle background thread failed for cycle %s", cycle_id
            )

    threading.Thread(target=_run, daemon=True, name="run-cycle-" + cycle_id).start()

    return RunCycleOut(
        cycle_id=cycle_id,
        status="started",
        message="Autonomous hedge cycle initiated",
        started_at=now,
    )


# ---------------------------------------------------------------------------
# P6-BE-12 - GET /workflow-state  (#158)
# ---------------------------------------------------------------------------


class WorkflowStateOut(BaseModel):
    """Current workflow state snapshot for one cycle."""

    cycle_id: str
    current_node: str
    status: str
    detail: dict[str, Any] | None = None
    updated_at: _dt.datetime | None = None


@router.get("/workflow-state", response_model=WorkflowStateOut)
def get_workflow_state(
    cycle_id: str | None = Query(default=None, description="Cycle to inspect; omit for latest"),
    engine: Engine = Depends(get_readback_engine),
) -> WorkflowStateOut:
    """Return the current workflow state (P6-BE-12 / #158).

    cycle_id is optional; omitting it returns the most-recently updated cycle.
    Returns 404 when no state has been persisted yet.
    """
    from sqlalchemy import MetaData, Table, desc, select

    from backend.db.workflow_repo import WorkflowStateRecord

    repo = WorkflowRepository(engine)

    if cycle_id is not None:
        state = repo.get_state(cycle_id)
    else:
        with engine.connect() as conn:
            meta = MetaData()
            tbl = Table("workflow_state", meta, autoload_with=engine)
            row = (
                conn.execute(
                    select(tbl).order_by(desc(tbl.c.updated_at), desc(tbl.c.id)).limit(1)
                )
                .mappings()
                .first()
            )
        state = (
            None
            if row is None
            else WorkflowStateRecord(
                id=row["id"],
                cycle_id=row["cycle_id"],
                current_node=row["current_node"],
                status=row["status"],
                detail=row["detail"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

    if state is None:
        raise HTTPException(status_code=404, detail="No workflow state found")

    return WorkflowStateOut(
        cycle_id=state.cycle_id,
        current_node=state.current_node,
        status=state.status,
        detail=state.detail,
        updated_at=state.updated_at,
    )


# ---------------------------------------------------------------------------
# P6-BE-12 - GET /workflow-state/stream  SSE  (#158)
# ---------------------------------------------------------------------------

_TERMINAL_NODES: frozenset[str] = frozenset({"COMPLETED", "FAILED"})
_LAST_PIPELINE_NODE = "MONITORING"


@router.get("/workflow-state/stream")
def stream_workflow_state(
    cycle_id: str | None = Query(default=None, description="Cycle to stream; omit for latest"),
    poll_interval_s: float = Query(default=0.5, ge=0.0, le=10.0),
    engine: Engine = Depends(get_readback_engine),
) -> Any:
    """SSE stream of workflow-state transitions (P6-BE-12 / #158).

    Emits one ``data: <JSON>`` Server-Sent Event per new row in
    ``workflow_transitions`` for the requested cycle (or the most-recently
    active cycle when cycle_id is omitted).

    Each event body is a JSON object with keys cycle_id, node, status, ts.

    The stream closes automatically when:

    * the cycle reaches a terminal node (COMPLETED / FAILED); or
    * the MONITORING EXIT transition is emitted.
    """
    import json
    import time

    from fastapi.responses import StreamingResponse

    def _event_generator():
        repo = WorkflowRepository(engine)
        last_id: int = 0
        resolved_id: str | None = cycle_id
        deadline = time.monotonic() + 30.0

        while True:
            # Resolve the cycle_id lazily (omitted -> most-recent)
            if resolved_id is None:
                if time.monotonic() > deadline:
                    return
                try:
                    from sqlalchemy import MetaData, Table, desc, select
                    with engine.connect() as conn:
                        meta = MetaData()
                        tbl = Table("workflow_state", meta, autoload_with=engine)
                        row = (
                            conn.execute(
                                select(tbl.c.cycle_id)
                                .order_by(desc(tbl.c.updated_at), desc(tbl.c.id))
                                .limit(1)
                            )
                            .mappings()
                            .first()
                        )
                    if row:
                        resolved_id = str(row["cycle_id"])
                except Exception:  # noqa: BLE001
                    pass

            # Poll for new transition rows
            if resolved_id is not None:
                try:
                    transitions = repo.get_transitions(resolved_id)
                except Exception:  # noqa: BLE001
                    transitions = []

                new_rows = [t for t in transitions if (t.id or 0) > last_id]
                should_close = False

                for t in new_rows:
                    last_id = t.id or last_id
                    payload = json.dumps(
                        {
                            "cycle_id": t.cycle_id,
                            "node": t.to_node,
                            "status": t.status,
                            "ts": (
                                t.transitioned_at.isoformat()
                                if t.transitioned_at
                                else None
                            ),
                        }
                    )
                    yield "data: " + payload + "\n\n"

                    if t.to_node in _TERMINAL_NODES:
                        should_close = True
                    elif t.to_node == _LAST_PIPELINE_NODE:
                        detail = t.detail or {}
                        if detail.get("phase") == "EXIT":
                            should_close = True

                if should_close:
                    return

            time.sleep(poll_interval_s)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
