"""Production smoke tests — task P8-FE-7."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_vercel_config_exists_and_valid() -> None:
    vercel_json = _REPO_ROOT / "frontend" / "vercel.json"
    assert vercel_json.exists(), "frontend/vercel.json is missing"
    data = json.loads(vercel_json.read_text(encoding="utf-8"))
    assert "rewrites" in data
    assert any(r.get("destination") == "/index.html" for r in data["rewrites"])


def test_health_smoke() -> None:
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "version" in data


def test_run_cycle_smoke() -> None:
    app = create_app()
    with TestClient(app) as client:
        res = client.post("/run-cycle", json={"force": True})
        assert res.status_code in (200, 202)
        data = res.json()
        assert "cycle_id" in data
        assert data["status"] in ("started", "completed", "running")


def test_frontend_dist_artifacts() -> None:
    dist_index = _REPO_ROOT / "frontend" / "dist" / "index.html"
    assert dist_index.exists(), "frontend/dist/index.html missing — run `npm run build`"
