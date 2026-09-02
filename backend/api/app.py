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
from backend.api import debug, health, stubs

_DEFAULT_CORS = ["http://localhost:3000", "http://localhost:5173"]


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
    app.include_router(stubs.router)
    return app


# Module-level instance for ``uvicorn backend.api.app:app``.
app = create_app()
