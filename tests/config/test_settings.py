"""Tests for ``backend.config.settings`` — tasks P1-DB-1 and P1-BE-4."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import Settings, get_settings, get_settings_or_exit


def test_db_creds_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings expose a non-empty DB DSN, and the app refuses to boot without it."""
    # 1. With the server-side .env in place, the DSN loads and is non-empty.
    settings = Settings()
    dsn = settings.database_url.get_secret_value()
    assert dsn, "DATABASE_URL resolved to an empty DSN"
    assert dsn.startswith("postgres"), f"unexpected DSN scheme in {dsn.split('://', 1)[0]!r}"

    # 2. The cached accessor returns the same, usable value.
    assert get_settings().database_url.get_secret_value() == dsn

    # 3. migration_dsn falls back to the pooled DSN until the unpooled one is set.
    assert settings.migration_dsn.startswith("postgres")

    # 4. App refuses to boot when DATABASE_URL is absent from every source.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_repr_hides_dsn() -> None:
    """The DSN never leaks through repr()/str() (secret-safe config)."""
    settings = Settings()
    secret = settings.database_url.get_secret_value()
    assert secret not in repr(settings)
    assert secret not in str(settings)


# --- P1-BE-4: typed loader, fail-fast, secret-safe ----------------------


def test_missing_required_key_raises_and_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing required key raises at load, and the error names that key."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "database_url" in str(excinfo.value).lower()


def test_get_settings_or_exit_reports_missing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``get_settings_or_exit`` turns the load failure into SystemExit(1) + a named key."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        get_settings_or_exit(lambda: Settings(_env_file=None))
    assert excinfo.value.code == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_all_secret_values_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """No secret field's value appears in repr()/str(), including LLM/Alpaca keys."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-SENTINEL")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "sk-featherless-SENTINEL")
    monkeypatch.setenv("ALPACA_API_KEY", "AK-SENTINEL")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "AS-SENTINEL")

    settings = Settings(_env_file=None)
    blob = repr(settings) + str(settings)
    for sentinel in ("SENTINEL", "sk-openrouter", "AK-SENTINEL", "AS-SENTINEL"):
        assert sentinel not in blob


def test_llm_provider_toggle_selects_base_url_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``llm_provider`` picks the matching base URL, model and key."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.example/v1")
    monkeypatch.setenv("OPENROUTER_MODEL", "or/model")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-key")
    monkeypatch.setenv("FEATHERLESS_BASE_URL", "https://featherless.example/v1")
    monkeypatch.setenv("FEATHERLESS_MODEL", "fl/model")

    openrouter = Settings(_env_file=None, llm_provider="openrouter")
    assert openrouter.llm_base_url == "https://openrouter.example/v1"
    assert openrouter.llm_model == "or/model"
    assert openrouter.llm_api_key is not None
    assert openrouter.llm_api_key.get_secret_value() == "or-key"

    featherless = Settings(_env_file=None, llm_provider="featherless")
    assert featherless.llm_base_url == "https://featherless.example/v1"
    assert featherless.llm_model == "fl/model"
    assert featherless.llm_api_key.get_secret_value() == "fl-key"


def test_cors_origins_parsed_to_list() -> None:
    """Comma-separated CORS origins become a clean list."""
    settings = Settings(
        _env_file=None,
        database_url="postgresql://u:p@h/db",
        cors_origins="http://a.test, http://b.test ,",
    )
    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]
