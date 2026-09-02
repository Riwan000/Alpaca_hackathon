"""Database async session and connection pool management — task P1-DB-14.

Configures async connection pooling using SQLAlchemy 2.0 and psycopg (v3)
with settings optimized for Neon and PgBouncer:
- Transaction pooling compatibility: disables server-side prepared statements
  cache via ``prepare_threshold=None`` to prevent statement collisions.
- Health checks: ``pool_pre_ping=True`` drops stale/recycled connections before handing them out.
- Bounded concurrency: ``pool_size`` + ``max_overflow`` enforce bounded DB connections.
- Clean lifecycle: FastAPI dependency ``get_db`` with automated commit/rollback/close.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import QueuePool

from backend.config import Settings, get_settings
from backend.db import normalize_driver

# Ensure Windows SelectorEventLoop is active for Psycopg async operation on Windows
if sys.platform == "win32":
    try:
        if not isinstance(
            asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy
        ):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass


_GLOBAL_ASYNC_ENGINE: AsyncEngine | None = None
_GLOBAL_SESSION_FACTORY: async_sessionmaker[AsyncSession] | None = None


def create_engine_and_pool(
    dsn: str | None = None,
    settings: Settings | None = None,
    **engine_overrides: Any,
) -> AsyncEngine:
    """Create a configured AsyncEngine with connection pooling and PgBouncer compatibility."""
    cfg = settings or get_settings()
    raw_dsn = dsn or cfg.database_url.get_secret_value()
    normalized_dsn = normalize_driver(raw_dsn)

    # Base pooling arguments
    connect_args = dict(engine_overrides.pop("connect_args", {}))

    # PgBouncer / Neon transaction pooler compatibility
    # When using psycopg with PgBouncer, prepare_threshold=None disables prepared statement caching
    if "postgresql" in normalized_dsn or "postgres" in normalized_dsn:
        connect_args.setdefault("prepare_threshold", None)

    pool_kwargs: dict[str, Any] = {
        "pool_size": engine_overrides.pop("pool_size", cfg.db_pool_size),
        "max_overflow": engine_overrides.pop("max_overflow", cfg.db_max_overflow),
        "pool_timeout": engine_overrides.pop("pool_timeout", cfg.db_pool_timeout),
        "pool_recycle": engine_overrides.pop("pool_recycle", cfg.db_pool_recycle),
        "pool_pre_ping": engine_overrides.pop("pool_pre_ping", cfg.db_pool_pre_ping),
        "connect_args": connect_args,
        **engine_overrides,
    }

    return create_async_engine(normalized_dsn, **pool_kwargs)


def get_async_engine(
    dsn: str | None = None,
    settings: Settings | None = None,
    recreate: bool = False,
    **engine_overrides: Any,
) -> AsyncEngine:
    """Return the singleton AsyncEngine, creating it if necessary."""
    global _GLOBAL_ASYNC_ENGINE, _GLOBAL_SESSION_FACTORY

    if _GLOBAL_ASYNC_ENGINE is None or recreate or dsn is not None:
        _GLOBAL_ASYNC_ENGINE = create_engine_and_pool(
            dsn=dsn, settings=settings, **engine_overrides
        )
        _GLOBAL_SESSION_FACTORY = async_sessionmaker(
            bind=_GLOBAL_ASYNC_ENGINE,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _GLOBAL_ASYNC_ENGINE


def get_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the async engine."""
    global _GLOBAL_SESSION_FACTORY
    if engine is not None:
        return async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    if _GLOBAL_SESSION_FACTORY is None:
        get_async_engine()
    assert _GLOBAL_SESSION_FACTORY is not None
    return _GLOBAL_SESSION_FACTORY


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an active AsyncSession, committing on exit or rolling back on error."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_async_engine() -> None:
    """Dispose of the singleton async engine and connection pool."""
    global _GLOBAL_ASYNC_ENGINE, _GLOBAL_SESSION_FACTORY
    if _GLOBAL_ASYNC_ENGINE is not None:
        await _GLOBAL_ASYNC_ENGINE.dispose()
        _GLOBAL_ASYNC_ENGINE = None
        _GLOBAL_SESSION_FACTORY = None


def get_pool_status(engine: AsyncEngine | None = None) -> dict[str, int]:
    """Return current connection pool metrics."""
    eng = engine or _GLOBAL_ASYNC_ENGINE
    if eng is None:
        return {"size": 0, "checked_in": 0, "checked_out": 0, "overflow": 0}
    pool = eng.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.checkedout() + pool.checkedin(),
    }
