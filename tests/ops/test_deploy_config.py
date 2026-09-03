"""Tests for deployment configuration — task P8-BE-5."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_and_procfile_exist() -> None:
    dockerfile = _REPO_ROOT / "Dockerfile"
    procfile = _REPO_ROOT / "Procfile"
    railway = _REPO_ROOT / "railway.json"
    render = _REPO_ROOT / "render.yaml"

    assert dockerfile.exists(), "Dockerfile missing"
    assert procfile.exists(), "Procfile missing"
    assert railway.exists(), "railway.json missing"
    assert render.exists(), "render.yaml missing"

    assert "uvicorn" in procfile.read_text(encoding="utf-8")
    assert "backend.api.app:app" in dockerfile.read_text(encoding="utf-8")


def test_railway_config_valid() -> None:
    railway = _REPO_ROOT / "railway.json"
    data = json.loads(railway.read_text(encoding="utf-8"))
    assert data["build"]["builder"] == "DOCKERFILE"
    assert data["deploy"]["healthcheckPath"] == "/health"


def test_health_endpoint_available() -> None:
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

