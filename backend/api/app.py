"""FastAPI application factory — task P1-BE-3.

``create_app()`` builds a fully wired :class:`fastapi.FastAPI` instance. It reads
:class:`backend.config.Settings` for CORS and environment, but tolerates an
incomplete environment (e.g. no ``DATABASE_URL`` in CI) by falling back to
permissive local defaults so ``/health`` always answers.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api import (
    alpaca,
    analyze,
    debug,
    decision_trail,
    exec_readback,
    execute,
    health,
    monitor,
    monitoring,
    pnl,
    readback,
    strategy_evaluate,
    strategy_readback,
    stubs,
    workflow,
)

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def _cors_origins() -> list[str]:
    try:
        from backend.config import get_settings

        return get_settings().cors_origins_list or _DEFAULT_CORS
    except Exception:
        return _DEFAULT_CORS


def create_app() -> FastAPI:
    """Construct and configure the ASGI application."""
    app = FastAPI(
        title="Autonomous Adaptive Portfolio Hedge Agent",
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(debug.router)
    app.include_router(readback.router)
    app.include_router(analyze.router)
    app.include_router(strategy_readback.router)
    app.include_router(strategy_evaluate.router)
    app.include_router(exec_readback.router)
    app.include_router(execute.router)
    app.include_router(workflow.router)
    app.include_router(monitoring.router)
    app.include_router(monitor.router)
    app.include_router(pnl.router)
    app.include_router(decision_trail.router)
    app.include_router(alpaca.router)
    app.include_router(stubs.router)
    _wire_monitor_scheduler(app)
    return app


def _wire_monitor_scheduler(app: FastAPI) -> None:
    """Start the demo monitor tick on boot, gated by ``Settings.enable_monitor_scheduler``.

    Off by default (task P7-BE-9): the many existing tests build
    ``TestClient(create_app())`` directly and must not get a background timer
    thread for free. A deployment opts in by setting
    ``ENABLE_MONITOR_SCHEDULER=true`` in its environment (Railway's, in this
    repo's case — ``railway.json`` declares no environment variables itself, so
    this is set in the Railway service's own env config, not the repo).
    """

    @app.on_event("startup")
    def _start_monitor_scheduler() -> None:  # pragma: no cover - exercised via the flag
        try:
            from backend.config import get_settings

            if not get_settings().enable_monitor_scheduler:
                return
        except Exception:
            return
        monitor.install_demo_monitor_tick()
        monitor.get_monitor_scheduler().start()

    @app.on_event("shutdown")
    def _stop_monitor_scheduler() -> None:  # pragma: no cover - exercised via the flag
        monitor.get_monitor_scheduler().stop()


# Module-level instance for ``uvicorn backend.api.app:app``.
app = create_app()
