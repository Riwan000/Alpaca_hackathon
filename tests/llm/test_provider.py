"""Tests for the ``LLM_PROVIDER`` abstraction — task P1-BE-5.

No network: only the resolved base URL / model / key are asserted, plus that an
OpenAI-compatible client is constructed against the right base URL.
"""

from __future__ import annotations

import pytest

from backend.config import Settings
from backend.llm import get_llm_client, resolve_model, resolve_provider

_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/db",
    "OPENROUTER_API_KEY": "or-key",
    "OPENROUTER_BASE_URL": "https://openrouter.test/api/v1",
    "OPENROUTER_MODEL": "openrouter/default-model",
    "FEATHERLESS_API_KEY": "fl-key",
    "FEATHERLESS_BASE_URL": "https://featherless.test/v1",
    "FEATHERLESS_MODEL": "featherless/default-model",
}


def _settings(provider: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LLM_PROVIDER", provider)
    return Settings(_env_file=None)


@pytest.mark.parametrize(
    ("provider", "base_url", "model", "key"),
    [
        ("openrouter", "https://openrouter.test/api/v1", "openrouter/default-model", "or-key"),
        ("featherless", "https://featherless.test/v1", "featherless/default-model", "fl-key"),
    ],
)
def test_toggle(
    provider: str,
    base_url: str,
    model: str,
    key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ``LLM_PROVIDER`` value selects the matching base URL + model + key."""
    settings = _settings(provider, monkeypatch)

    cfg = resolve_provider(settings)
    assert cfg.name == provider
    assert cfg.base_url == base_url
    assert cfg.model == model
    assert cfg.api_key == key

    client = get_llm_client(settings)
    assert str(client.base_url).rstrip("/") == base_url.rstrip("/")


def test_model_alias_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-default aliases resolve through MODEL_MAP; unknown aliases raise."""
    settings = _settings("openrouter", monkeypatch)

    assert resolve_model("default", settings) == "openrouter/default-model"
    assert resolve_model("fast", settings) == "anthropic/claude-3.5-haiku"

    monkeypatch.setenv("LLM_PROVIDER", "featherless")
    featherless = Settings(_env_file=None)
    assert resolve_model("fast", featherless) == "meta-llama/Meta-Llama-3.1-8B-Instruct"

    with pytest.raises(KeyError):
        resolve_model("does-not-exist", settings)


def test_blank_or_whitespace_key_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty or whitespace-only key resolves to ``None`` (skip live calls)."""
    _settings("openrouter", monkeypatch)
    for blank in ("", "   ", "\t\n"):
        monkeypatch.setenv("OPENROUTER_API_KEY", blank)
        assert resolve_provider(Settings(_env_file=None)).api_key is None


def test_client_key_is_never_the_secret_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_provider hands back the raw key string, not a SecretStr."""
    settings = _settings("openrouter", monkeypatch)
    cfg = resolve_provider(settings)
    assert isinstance(cfg.api_key, str)
    assert "Secret" not in repr(cfg.api_key)
