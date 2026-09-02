"""Synchronous persistence seam over the Alembic-managed schema — task P2-DB-1.

Phase 2's quant engine is pure (no I/O). The only thing it needs from the
database is a way to round-trip a *computed* portfolio snapshot: compute a
metric set, ``save`` it, read it back unchanged. This module provides exactly
that seam and nothing more.

Phase 3 (P3-DB-2 / P3-DB-3) grows this into the full async snapshot + positions
repository that also carries the risk-metric columns; see
``docs/adr/0001-risk-metrics-storage.md`` for why those metrics land on
``portfolio_snapshots`` rather than a dedicated table.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal

from sqlalchemy import MetaData, RowMapping, Table, func, insert, select
from sqlalchemy.engine import Engine

_TABLE_NAME = "portfolio_snapshots"


@dataclasses.dataclass(frozen=True)
class PortfolioSnapshotRecord:
    """One ``portfolio_snapshots`` row.

    ``id`` is assigned by the database on :meth:`PortfolioSnapshotRepository.save`.
    ``ts`` is excluded from equality: the column carries a ``server_default`` of
    ``now()`` and SQLite drops timezone info on read, so a round-trip check
    should assert metric identity, not the timestamp.
    """

    cycle_id: str
    total_value: decimal.Decimal
    cash: decimal.Decimal
    equity: decimal.Decimal
    buying_power: decimal.Decimal
    ts: _dt.datetime = dataclasses.field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc), compare=False
    )
    id: int | None = None


class PortfolioSnapshotRepository:
    """CRUD-lite access to ``portfolio_snapshots`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_TABLE_NAME, MetaData(), autoload_with=engine)

    def save(self, record: PortfolioSnapshotRecord) -> PortfolioSnapshotRecord:
        """Insert ``record`` and return a copy carrying the assigned ``id``."""
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._table).values(
                    cycle_id=record.cycle_id,
                    ts=record.ts,
                    total_value=record.total_value,
                    cash=record.cash,
                    equity=record.equity,
                    buying_power=record.buying_power,
                )
            )
            new_id = int(result.inserted_primary_key[0])
        return dataclasses.replace(record, id=new_id)

    def get(self, snapshot_id: int) -> PortfolioSnapshotRecord | None:
        """Return the snapshot with ``snapshot_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._table).where(self._table.c.id == snapshot_id))
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def latest(self) -> PortfolioSnapshotRecord | None:
        """Return the most recent snapshot by ``ts`` (``id`` breaks ties)."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(self._table).order_by(
                        self._table.c.ts.desc(), self._table.c.id.desc()
                    )
                )
                .mappings()
                .first()
            )
        return self._to_record(row)

    def count(self) -> int:
        """Number of rows currently in ``portfolio_snapshots``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(select(func.count()).select_from(self._table)).scalar_one()
            )

    @staticmethod
    def _to_record(row: RowMapping | None) -> PortfolioSnapshotRecord | None:
        if row is None:
            return None
        return PortfolioSnapshotRecord(
            cycle_id=row["cycle_id"],
            total_value=row["total_value"],
            cash=row["cash"],
            equity=row["equity"],
            buying_power=row["buying_power"],
            ts=row["ts"],
            id=int(row["id"]),
        )
