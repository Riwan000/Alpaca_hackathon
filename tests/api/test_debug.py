"""Tests for ``GET /debug/llm`` — task P1-BE-5 confirm route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


def test_debug_llm_echoes_resolved_provider() -> None:
    """The debug route reports provider/model/base_url and never the key itself."""
    client = TestClient(create_app())
    response = client.get("/debug/llm")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] in {"openrouter", "featherless"}
    assert body["base_url"].startswith("http")
    assert body["model"]
    assert set(body) == {"provider", "model", "base_url", "api_key_configured"}
    assert isinstance(body["api_key_configured"], bool)


def test_debug_llm_degrades_when_settings_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route stays 200 even if settings fail to load (e.g. missing DATABASE_URL)."""
    import backend.llm.provider as provider_mod

    def _boom() -> None:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(provider_mod, "get_settings", _boom)

    response = TestClient(create_app()).get("/debug/llm")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] in {"openrouter", "featherless"}
    assert body["api_key_configured"] is False
