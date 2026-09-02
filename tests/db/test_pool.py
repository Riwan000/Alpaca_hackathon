"""Connection pooling and async session tests — task P1-DB-14.

Tests that async connection pooling is bounded, concurrent tasks do not exceed
the configured pool limit, and connections are recycled without leaks.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.db.session import (
    close_async_engine,
    create_engine_and_pool,
    get_async_engine,
    get_db,
    get_pool_status,
    get_session_factory,
)

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass


@pytest.mark.asyncio
async def test_pool_bounded() -> None:
    """Task P1-DB-14: 50 concurrent queries never exceed pool_size (+ max_overflow) and do not leak."""
    settings = get_settings()
    pool_size = 10
    max_overflow = 5
    total_allowed = pool_size + max_overflow

    engine = create_engine_and_pool(
        settings=settings,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=60.0,
        pool_pre_ping=True,
    )

    peak_checked_out = 0
    lock = asyncio.Lock()

    async def worker(worker_id: int) -> int:
        nonlocal peak_checked_out
        async with engine.connect() as conn:
            async with lock:
                current_checked_out = engine.pool.checkedout()
                if current_checked_out > peak_checked_out:
                    peak_checked_out = current_checked_out
                # Assert at every sample that we never exceed total allowed
                assert current_checked_out <= total_allowed, (
                    f"Checked out connections ({current_checked_out}) exceeded "
                    f"allowed limit ({total_allowed})"
                )

            # Query database
            res = await conn.execute(text("SELECT 1 AS num;"))
            row = res.scalar()
            return int(row)

    try:
        # Launch 50 concurrent queries
        tasks = [worker(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 50
        assert all(r == 1 for r in results)
        assert peak_checked_out <= total_allowed
        assert peak_checked_out > 0

        # Verify no leaks after completion: all connections returned to pool
        await asyncio.sleep(0.05)
        status = get_pool_status(engine)
        assert status["checked_out"] == 0, (
            f"Expected 0 checked out connections after completion, found {status['checked_out']}"
        )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pgbouncer_compatibility_settings() -> None:
    """Verify PgBouncer-compatible settings and connection arguments."""
    settings = get_settings()
    engine = create_engine_and_pool(settings=settings)
    try:
        # Check pool parameters
        assert engine.pool.size() == settings.db_pool_size
        assert engine.pool._max_overflow == settings.db_max_overflow
        assert engine.pool._timeout == settings.db_pool_timeout
        assert engine.pool._recycle == settings.db_pool_recycle
        assert engine.pool._pre_ping is True

        # Connect and run query
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fastapi_get_db_dependency() -> None:
    """Verify get_db dependency yields a valid session and manages transactions cleanly."""
    async for session in get_db():
        assert isinstance(session, AsyncSession)
        res = await session.execute(text("SELECT 42 AS answer"))
        assert res.scalar() == 42
    await close_async_engine()
