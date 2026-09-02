"""Task P1-OPS-6 — first runnable checkpoint.

After P1-BE-1..3 + P1-OPS-1: ``make dev`` serves ``/health`` and the health +
settings tests pass. This bundles that gate into one automated check so the
checkpoint stays green as later phases land.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend import __version__
from backend.api import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAKEFILE = _REPO_ROOT / "Makefile"


def test_referenced_checkpoint_tests_exist() -> None:
    for rel in ("tests/api/test_health.py", "tests/config/test_settings.py"):
        assert (_REPO_ROOT / rel).is_file(), f"checkpoint test {rel} is missing"


def test_health_endpoint_answers() -> None:
    """``GET /health`` → 200 with a version, even with an incomplete env."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert set(body["build"]) == {"sha", "time", "environment"}


def test_make_dev_targets_port_8000_and_the_app_factory() -> None:
    text = _MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^dev\s*:(?!=).*?(?=^\S)", text, re.DOTALL | re.MULTILINE)
    assert match, "Makefile has no `dev` target"
    recipe = match.group(0)
    assert "uvicorn" in recipe, "`make dev` does not launch uvicorn"
    assert "backend.api.app:app" in recipe, "`make dev` does not point at the app factory"
    assert "8000" in recipe or "$(PORT)" in recipe, "`make dev` does not bind :8000"
