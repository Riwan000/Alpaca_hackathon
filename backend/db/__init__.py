"""Database layer — task P1-DB-2.

Schema migrations live in ``backend/db/migrations`` (Alembic). The ORM models
and repositories land with the later ``P1-DB-*`` tasks and will extend this
package.
"""

from __future__ import annotations

import os

_PSYCOPG_DRIVER = "postgresql+psycopg"
_OVERRIDE_ENV_VAR = "ALEMBIC_DATABASE_URL"

__all__ = [
    "migration_url",
    "normalize_driver",
    "OVERRIDE_ENV_VAR",
    "get_async_engine",
    "get_session_factory",
    "get_db",
    "close_async_engine",
    "get_pool_status",
    "create_engine_and_pool",
]


OVERRIDE_ENV_VAR = _OVERRIDE_ENV_VAR


def normalize_driver(url: str) -> str:
    """Return ``url`` with an explicit SQLAlchemy driver.

    Neon (and most managed Postgres) hand out bare ``postgresql://`` DSNs.
    SQLAlchemy needs the driver spelled out and psycopg v3 is the one this
    project depends on. Non-Postgres URLs — e.g. the ``sqlite://`` scratch DB
    used by the migration test — pass through unchanged.
    """
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return f"{_PSYCOPG_DRIVER}://{url[len(scheme):]}"
    return url


def migration_url() -> str:
    """The DSN Alembic should migrate against, driver-normalised.

    Precedence:

    1. ``$ALEMBIC_DATABASE_URL`` — an explicit override; the test harness points
       this at a throwaway database.
    2. :attr:`backend.config.Settings.migration_dsn` — the Neon direct/unpooled
       endpoint from the server-side ``.env`` (task P1-DB-1).
    """
    override = os.getenv(_OVERRIDE_ENV_VAR)
    if override is not None:
        override = override.strip()
        if not override:
            # Present but blank: fail closed rather than silently migrating the
            # production database.
            raise ValueError(f"{_OVERRIDE_ENV_VAR} is set but empty")
        return normalize_driver(override)

    from backend.config import get_settings

    return normalize_driver(get_settings().migration_dsn)


def get_async_engine(*args, **kwargs):
    from backend.db.session import get_async_engine as _get_engine
    return _get_engine(*args, **kwargs)


def get_session_factory(*args, **kwargs):
    from backend.db.session import get_session_factory as _get_sf
    return _get_sf(*args, **kwargs)


def get_db():
    from backend.db.session import get_db as _get_db
    return _get_db()


def close_async_engine(*args, **kwargs):
    from backend.db.session import close_async_engine as _close_engine
    return _close_engine(*args, **kwargs)


def get_pool_status(*args, **kwargs):
    from backend.db.session import get_pool_status as _get_status
    return _get_status(*args, **kwargs)


def create_engine_and_pool(*args, **kwargs):
    from backend.db.session import create_engine_and_pool as _create_pool
    return _create_pool(*args, **kwargs)

