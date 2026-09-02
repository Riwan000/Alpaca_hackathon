"""Tests for ``backend.config.settings`` — task P1-DB-1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import Settings, get_settings


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
