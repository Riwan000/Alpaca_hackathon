"""Application settings — tasks P1-DB-1 and P1-BE-4.

Typed configuration loaded from the environment and the server-side ``.env``
file (git-ignored). The app refuses to boot when a required key is missing or
empty: constructing :class:`Settings` raises ``pydantic.ValidationError`` and
:func:`get_settings_or_exit` turns that into a clean ``SystemExit`` that names
the offending key.

Secrets are held as ``SecretStr`` so they never appear in ``repr(settings)`` or
log output. Downstream code reads the raw value explicitly, e.g.
``settings.database_url.get_secret_value()``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/config/settings.py -> parents[2] is the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"

LlmProvider = Literal["openrouter", "featherless"]


class Settings(BaseSettings):
    """Process-wide configuration.

    Only ``database_url`` is strictly required — the app cannot run without a
    database. Provider credentials (LLM, Alpaca, market data) are optional at
    load time so the process can boot in a degraded mode; the code path that
    actually needs a key checks for it at its own boundary.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database (required) ------------------------------------------------
    # Pooled connection string — application runtime (Neon pooler endpoint).
    database_url: SecretStr = Field(..., min_length=1)

    # Direct / unpooled connection string — migrations only. Optional; callers
    # fall back to the pooled DSN.
    database_url_unpooled: SecretStr | None = None

    # Connection pooling settings (P1-DB-14) — tuned for Neon / PgBouncer.
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=30.0, ge=0.1)
    db_pool_recycle: int = Field(default=1800, ge=1)
    db_pool_pre_ping: bool = Field(default=True)

    # --- LLM provider (P1-BE-5) ------------------------------------------
    llm_provider: LlmProvider = "openrouter"

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-3.5-sonnet"

    featherless_api_key: SecretStr | None = None
    featherless_base_url: str = "https://api.featherless.ai/v1"
    featherless_model: str = "meta-llama/Meta-Llama-3.1-70B-Instruct"

    # --- Alpaca broker / market data -----------------------------------
    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets/v2"
    alpaca_paper: bool = True

    # --- External data providers (optional / fallback) ---------------
    finnhub_api_key: SecretStr | None = None
    news_api_key: SecretStr | None = None

    # --- Backend server / API ----------------------------------------
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    environment: str = "development"
    log_level: str = "INFO"
    # Comma-separated in the environment; use :pyattr:`cors_origins_list`.
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"

    # --- Risk engine / autonomous hedge parameters -----------------
    max_hedge_budget_pct: float = Field(default=0.05, gt=0, le=1)
    drawdown_trigger_pct: float = Field(default=0.05, gt=0, le=1)
    hedge_drift_threshold_pct: float = Field(default=0.05, gt=0, le=1)
    reassessment_cooldown_seconds: int = Field(default=300, ge=0)

    # --- Monitoring scheduler (BRD §24) -------------------------------
    # Off by default: ``create_app()`` runs under many tests via a plain
    # ``TestClient(create_app())`` and must not spin up a background timer
    # thread unless a deployment explicitly opts in (task P7-BE-9).
    enable_monitor_scheduler: bool = False

    # --- Derived views -------------------------------------------------
    @property
    def migration_dsn(self) -> str:
        """DSN for schema migrations — prefers the direct/unpooled endpoint."""
        target = self.database_url_unpooled or self.database_url
        return target.get_secret_value()

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS allow-list, parsed from the comma-separated env value."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_base_url(self) -> str:
        """Base URL of the OpenAI-compatible endpoint for the active provider."""
        return (
            self.openrouter_base_url
            if self.llm_provider == "openrouter"
            else self.featherless_base_url
        )

    @property
    def llm_model(self) -> str:
        """Default model id for the active provider."""
        return (
            self.openrouter_model
            if self.llm_provider == "openrouter"
            else self.featherless_model
        )

    @property
    def llm_api_key(self) -> SecretStr | None:
        """API key for the active provider (``None`` when unset)."""
        return (
            self.openrouter_api_key
            if self.llm_provider == "openrouter"
            else self.featherless_api_key
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, process-wide :class:`Settings` instance."""
    return Settings()


def get_settings_or_exit(
    settings_factory: Callable[[], Settings] = get_settings,
) -> Settings:
    """Load settings, or exit the process naming the missing/invalid keys.

    Use this at real entrypoints (the ASGI app, CLI commands) so an operator
    sees ``missing or invalid required setting(s): DATABASE_URL`` instead of a
    stack trace.
    """
    try:
        return settings_factory()
    except ValidationError as exc:
        keys = sorted({str(err["loc"][0]).upper() for err in exc.errors() if err.get("loc")})
        joined = ", ".join(keys) or "(unknown)"
        print(
            f"configuration error: missing or invalid required setting(s): {joined}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
