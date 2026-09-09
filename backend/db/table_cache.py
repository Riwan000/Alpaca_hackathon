"""Process-wide, per-engine ``Table`` reflection cache.

Every read-repository in :mod:`backend.db` used to reflect its tables via
``Table(name, MetaData(), autoload_with=engine)`` inside ``__init__`` — and
every API route builds a *fresh* repository instance per request. Against a
remote Postgres reached through a connection pooler (Neon), each reflection
costs several round-trip introspection queries (columns, PK, indexes, ...)
and was observed to take 10-15+ seconds, or hang outright, per request — the
more tables a repository reflects, the worse. The actual queries these
repositories run are fast; it was purely the per-request reflection tax.

:func:`get_table` fixes this by reflecting each table **once per engine** and
caching the resulting :class:`~sqlalchemy.Table` keyed by the engine
*instance* in a module-level :class:`weakref.WeakKeyDictionary`. (An earlier
draft tried stashing the cache on ``engine.info`` — SQLAlchemy's per-engine
dict attached for exactly this purpose in some releases — but
``Engine.info`` does not exist in the SQLAlchemy 2.0 line this project pins;
only ``Connection.info`` does, and a ``Connection`` is checked out fresh per
request, so it can't hold a cache across requests. A ``WeakKeyDictionary``
keyed by the engine object gives the same properties without that.) That
keeps the cache:

* **correct across tests** — the test suite overrides ``get_readback_engine``
  with a per-test scratch-DB engine (see ``backend/api/readback.py``); keying
  the cache off the engine instance itself (rather than a single
  process-global dict keyed by table name) means two different engines never
  share a reflected ``Table``, even when both happen to have a table of the
  same name.
* **thread-safe** — these sync repositories are constructed from FastAPI's
  threadpool, so concurrent first-requests can race to reflect the same table
  on the same engine. A lock around the check-and-populate step ensures only
  one thread ever reflects a given ``(engine, name, schema)`` and no other
  thread ever observes a partially-built ``Table``.
* **self-cleaning** — ``WeakKeyDictionary`` drops an engine's entry as soon as
  the engine itself is garbage collected; no separate teardown is needed, and
  the cache can never keep an otherwise-dead engine alive.
"""

from __future__ import annotations

import threading
import weakref

from sqlalchemy import MetaData, Table
from sqlalchemy.engine import Engine

# engine -> {(table_name, schema): reflected Table}
_CACHE: "weakref.WeakKeyDictionary[Engine, dict[tuple[str, str | None], Table]]" = (
    weakref.WeakKeyDictionary()
)

# Guards the check-and-populate step below. Reflection happens at most once
# per (engine, table) for the life of the process, so a single process-wide
# lock adds no meaningful contention on the hot (already-cached) path, which
# never acquires it.
_LOCK = threading.Lock()


def get_table(engine: Engine, name: str, *, schema: str | None = None) -> Table:
    """Return the reflected ``Table`` for ``name`` on ``engine``.

    Reflects at most once per ``(engine, name, schema)`` for the life of the
    process (or until ``engine`` is garbage collected); subsequent calls,
    including from other threads once the first reflection has completed,
    return the cached ``Table`` with no DB round trip.
    """
    key = (name, schema)

    per_engine = _CACHE.get(engine)
    if per_engine is not None:
        table = per_engine.get(key)
        if table is not None:
            return table

    with _LOCK:
        per_engine = _CACHE.get(engine)
        if per_engine is None:
            per_engine = {}
            _CACHE[engine] = per_engine

        table = per_engine.get(key)
        if table is None:
            table = Table(name, MetaData(), autoload_with=engine, schema=schema)
            per_engine[key] = table
        return table
