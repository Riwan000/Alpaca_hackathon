"""``GET /health`` — task P1-BE-3.

Liveness probe that also reports the running version and build provenance so a
deployed instance can be identified. Build fields come from the environment
(``BUILD_SHA`` / ``BUILD_TIME``, injected by CI) and fall back to ``"dev"``.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from backend import __version__

router = APIRouter(tags=["ops"])

_UNKNOWN = "dev"


class BuildInfo(BaseModel):
    sha: str
    time: str
    environment: str


class HealthResponse(BaseModel):
    status: str
    version: str
    build: BuildInfo


def _build_info(environment: str = _UNKNOWN) -> BuildInfo:
    return BuildInfo(
        sha=os.getenv("BUILD_SHA", _UNKNOWN),
        time=os.getenv("BUILD_TIME", _UNKNOWN),
        environment=environment,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return ``200`` with version and build info."""
    try:
        from backend.config import get_settings

        environment = get_settings().environment
    except Exception:
        environment = _UNKNOWN
    return HealthResponse(status="ok", version=__version__, build=_build_info(environment))
