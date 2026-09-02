"""Alembic migration environment — task P1-DB-2.

The target database is resolved by :func:`backend.db.migration_url` — the Neon
direct/unpooled DSN from the server-side ``.env``, or an
``ALEMBIC_DATABASE_URL`` override (used by the test harness against a scratch
DB). No ORM metadata is wired yet; autogenerate support arrives with the schema
tasks (P1-DB-3+).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# backend/db/migrations/env.py -> parents[3] is the repository root. Make it
# importable regardless of the invoking CWD or ini interpolation support.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.db import migration_url  # noqa: E402  (after sys.path bootstrap)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No models registered yet — schema starts at P1-DB-3.
target_metadata = None


def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without connecting to a database."""
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = create_engine(migration_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                # SQLite (the local scratch DB) cannot ALTER in place.
                render_as_batch=connection.dialect.name == "sqlite",
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
