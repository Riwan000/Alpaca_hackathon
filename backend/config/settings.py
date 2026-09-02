"""Application settings — task P1-DB-1.

Typed configuration loaded from the environment and the server-side ``.env``
file (git-ignored). The app refuses to boot when a required secret is missing
or empty: constructing :class:`Settings` raises ``pydantic.ValidationError``.

Secrets are held as ``SecretStr`` so they never appear in ``repr(settings)`` or
log output. Downstream code reads the raw value explicitly, e.g.
``settings.database_url.get_secret_value()``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/config/settings.py -> parents[2] is the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Process-wide configuration.

    Only the database credentials are modelled here; the full typed loader
    (LLM, Alpaca, risk parameters) lands with P1-BE-4 and extends this class.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Pooled connection string — application runtime (Neon pooler endpoint).
    database_url: SecretStr = Field(..., min_length=1)

    # Direct / unpooled connection string — migrations only. Optional until
    # migration tooling lands (P1-DB-2); callers fall back to the pooled DSN.
    database_url_unpooled: SecretStr | None = None

    # Connection pooling settings (P1-DB-14) — tuned for Neon / PgBouncer
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=30.0, ge=0.1)
    db_pool_recycle: int = Field(default=1800, ge=1)
    db_pool_pre_ping: bool = Field(default=True)


    @property
    def migration_dsn(self) -> str:
        """DSN for schema migrations — prefers the direct/unpooled endpoint."""
        target = self.database_url_unpooled or self.database_url
        return target.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, process-wide :class:`Settings` instance."""
    return Settings()
