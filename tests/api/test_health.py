"""Tests for ``GET /health`` — task P1-BE-3."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import __version__
from backend.api import create_app


def test_health_ok() -> None:
    """``GET /health`` returns 200 with a version and build block."""
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert set(body["build"]) == {"sha", "time", "environment"}


def test_health_reports_build_sha_from_env(monkeypatch) -> None:
    """CI-injected build metadata surfaces in the response."""
    monkeypatch.setenv("BUILD_SHA", "abc1234")
    monkeypatch.setenv("BUILD_TIME", "2026-09-02T12:00:00Z")

    client = TestClient(create_app())
    build = client.get("/health").json()["build"]

    assert build["sha"] == "abc1234"
    assert build["time"] == "2026-09-02T12:00:00Z"
