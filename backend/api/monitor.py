"""Monitoring tick — task P7-BE-9 (BRD §24, §37 Scene 8).

* ``POST /monitor`` — run the Level-1 deterministic checks once against the
  current hedge context and report the fired triggers (or none), plus whether
  they clear the Level-1 → Level-2 escalation gate. When an engine is wired the
  tick also persists its ``monitoring_events`` / ``monitoring_state`` rows, so
  ``GET /monitoring/events`` and the frontend panel reflect it immediately.

* :class:`MonitorScheduler` — a tiny in-process periodic runner. The demo
  registers one job (:func:`install_demo_monitor_tick`) that fires the tick on an
  interval so the "market stabilizes → hedge reduced" story plays hands-off; it
  is **not** started inside :func:`backend.api.app.create_app` (no background
  threads in tests) — an entrypoint calls :meth:`MonitorScheduler.start`.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import logging
import threading
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.agents.monitoring.reassessment import should_escalate
from backend.api.readback import get_readback_engine
from backend.models.hedge_context import HedgeContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoring"])

__all__ = [
    "MonitorJob",
    "MonitorScheduler",
    "get_monitor_context",
    "get_monitor_scheduler",
    "install_demo_monitor_tick",
    "router",
]


# --------------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------------- #


class MonitorTickIn(BaseModel):
    cycle_id: str | None = None


class TriggerOut(BaseModel):
    trigger_type: str
    observed_value: float | None = None
    threshold: float | None = None
    detail: str | None = None
    breached: bool = True


class MonitorTickOut(BaseModel):
    cycle_id: str | None = None
    as_of: _dt.datetime
    triggers: list[TriggerOut] = []
    active_triggers: list[str] = []
    escalate: bool = False
    emergency: bool = False
    bypassed_cooldown: bool = False
    escalation_reason: str = ""
    persisted: bool = False
    note: str | None = None


# --------------------------------------------------------------------------- #
# context source (overridable in tests)
# --------------------------------------------------------------------------- #

MonitorContextProvider = Callable[[str | None], "HedgeContext | None"]


def _live_monitor_context(cycle_id: str | None) -> HedgeContext | None:
    """Best-effort live hedge context for a manual tick.

    Builds the same Phase-3 context the orchestrator's ``ANALYZING`` node does,
    with ``current_hedge`` reconstructed from order history the same way
    ``POST /analyze`` does — a DB-unavailable environment still degrades to the
    empty default rather than failing the tick. Returns ``None`` (rather than
    raising) when credentials / data are missing so the endpoint still answers
    on a cold environment.
    """
    try:
        from backend.agents.assembler import assemble_hedge_context
        from backend.agents.ingest import build_live_analysis_inputs
        from backend.api.readback import get_readback_engine

        try:
            engine = get_readback_engine()
        except Exception:  # noqa: BLE001 - no DB configured; keep current_hedge empty
            logger.warning("POST /monitor: readback engine unavailable for current_hedge", exc_info=True)
            engine = None

        inputs = build_live_analysis_inputs(engine=engine)
        if cycle_id and inputs.cycle_id != cycle_id:
            inputs = inputs.model_copy(update={"cycle_id": cycle_id})
        return assemble_hedge_context(inputs)
    except Exception:  # noqa: BLE001 - a manual tick must not 500 on missing creds
        logger.warning("POST /monitor: could not build a live hedge context", exc_info=True)
        return None


def get_monitor_context() -> MonitorContextProvider:
    """FastAPI dependency — the hedge-context source for ``POST /monitor``.

    Overridden in tests with a factory that returns a crafted context.
    """
    return _live_monitor_context


# --------------------------------------------------------------------------- #
# POST /monitor
# --------------------------------------------------------------------------- #


@router.post("/monitor", response_model=MonitorTickOut)
def monitor_tick(
    payload: MonitorTickIn = MonitorTickIn(),
    engine: Engine = Depends(get_readback_engine),
    context_provider: MonitorContextProvider = Depends(get_monitor_context),
) -> MonitorTickOut:
    """Run Level-1 checks once and report the fired triggers (task P7-BE-9)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    ctx = context_provider(payload.cycle_id)
    if ctx is None:
        return MonitorTickOut(
            cycle_id=payload.cycle_id,
            as_of=now,
            note="no hedge context available (missing market data / credentials)",
        )

    repo, persisted = _monitoring_repo(engine)
    try:
        from backend.agents.monitoring.agent import MonitoringAgent

        agent = MonitoringAgent(repo=repo) if persisted else MonitoringAgent()
        state = agent.evaluate(ctx)
    except Exception:  # noqa: BLE001 - Level-1 must not 500 the tick
        logger.exception("POST /monitor: Level-1 evaluation failed")
        return MonitorTickOut(
            cycle_id=ctx.cycle_id, as_of=now, note="Level-1 checks unavailable"
        )

    esc = should_escalate(state)
    return MonitorTickOut(
        cycle_id=ctx.cycle_id,
        as_of=state.as_of,
        triggers=[
            TriggerOut(
                trigger_type=obs.trigger_type.value,
                observed_value=obs.observed_value,
                threshold=obs.threshold,
                detail=obs.detail,
                breached=obs.breached,
            )
            for obs in state.trigger_history
        ],
        active_triggers=[t.value for t in state.active_triggers],
        escalate=esc.escalate,
        emergency=esc.emergency,
        bypassed_cooldown=esc.bypassed_cooldown,
        escalation_reason=esc.reason,
        persisted=persisted,
    )


def _monitoring_repo(engine: Engine | None) -> tuple[Any | None, bool]:
    if engine is None:
        return None, False
    try:
        from backend.db.monitoring_repo import MonitoringRepository

        return MonitoringRepository(engine), True
    except Exception:  # noqa: BLE001 - unmigrated / cold DB
        logger.warning("POST /monitor: monitoring tables unavailable; tick will not persist")
        return None, False


# --------------------------------------------------------------------------- #
# scheduler (demo tick)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class MonitorJob:
    """One registered periodic job."""

    job_id: str
    interval_seconds: float
    fn: Callable[[], Any]
    _timer: "threading.Timer | None" = dataclasses.field(default=None, repr=False)


class MonitorScheduler:
    """A minimal in-process periodic runner for the demo monitoring tick.

    Not a general scheduler — one re-arming :class:`threading.Timer` per job.
    ``register`` records the job; ``start`` arms every registered job; ``stop``
    cancels them.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, MonitorJob] = {}
        self._running = False

    @property
    def jobs(self) -> dict[str, MonitorJob]:
        return dict(self._jobs)

    @property
    def running(self) -> bool:
        return self._running

    def register(
        self, job_id: str, interval_seconds: float, fn: Callable[[], Any]
    ) -> MonitorJob:
        """Register (or replace) a periodic job. Does not start it."""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        job = MonitorJob(job_id=job_id, interval_seconds=float(interval_seconds), fn=fn)
        self._jobs[job_id] = job
        if self._running:
            self._arm(job)
        return job

    def unregister(self, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None and job._timer is not None:
            job._timer.cancel()

    def start(self) -> None:
        self._running = True
        for job in self._jobs.values():
            self._arm(job)

    def stop(self) -> None:
        self._running = False
        for job in self._jobs.values():
            if job._timer is not None:
                job._timer.cancel()
                job._timer = None

    def _arm(self, job: MonitorJob) -> None:
        def _fire() -> None:
            try:
                job.fn()
            except Exception:  # noqa: BLE001 - a job error must not kill the loop
                logger.exception("MonitorScheduler: job %s raised", job.job_id)
            finally:
                if self._running:
                    self._arm(job)

        timer = threading.Timer(job.interval_seconds, _fire)
        timer.daemon = True
        job._timer = timer
        timer.start()


_SCHEDULER = MonitorScheduler()

#: The job id the demo tick registers under.
DEMO_TICK_JOB_ID = "demo-monitor-tick"


def get_monitor_scheduler() -> MonitorScheduler:
    """The process-wide :class:`MonitorScheduler` singleton."""
    return _SCHEDULER


def install_demo_monitor_tick(
    scheduler: MonitorScheduler | None = None,
    *,
    interval_seconds: float = 300.0,
    tick: Callable[[], Any] | None = None,
) -> MonitorJob:
    """Register the demo monitoring tick (task P7-BE-9). Call ``scheduler.start()``
    from an entrypoint to actually run it."""
    sched = scheduler or _SCHEDULER

    def _default_tick() -> None:
        from fastapi.testclient import TestClient

        from backend.api.app import create_app

        with TestClient(create_app()) as c:
            c.post("/monitor")

    return sched.register(
        DEMO_TICK_JOB_ID, interval_seconds, tick or _default_tick
    )
