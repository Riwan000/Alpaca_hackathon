"""Synchronous persistence seam over the Alembic-managed schema — tasks P2-DB-1, P3-DB-2.

Phase 2's quant engine is pure (no I/O). The only thing it needs from the
database is a way to round-trip a *computed* portfolio snapshot: compute a
metric set, ``save`` it, read it back unchanged (:meth:`~PortfolioSnapshotRepository.save`).

Phase 3 (P3-DB-2) adds the write path each analysis pass actually uses:
:meth:`~PortfolioSnapshotRepository.save_with_positions` persists the snapshot
row **and its N position rows in a single transaction** — a bad position rolls
the snapshot back with it, so a half-written pass never lands.

P3-DB-3 grows ``portfolio_snapshots`` — and this record — with the computed
risk-metric columns (``volatility`` / ``beta`` / ``drawdown``); see
``docs/adr/0001-risk-metrics-storage.md`` for why those metrics land on
``portfolio_snapshots`` rather than a dedicated table. They are nullable: an
early cycle may lack the history to compute them.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
from collections.abc import Sequence

from sqlalchemy import MetaData, RowMapping, Table, func, insert, select
from sqlalchemy.engine import Engine

_TABLE_NAME = "portfolio_snapshots"
_POSITIONS_TABLE_NAME = "positions"


@dataclasses.dataclass(frozen=True)
class PortfolioSnapshotRecord:
    """One ``portfolio_snapshots`` row.

    ``id`` is assigned by the database on :meth:`PortfolioSnapshotRepository.save`.
    ``ts`` is excluded from equality: the column carries a ``server_default`` of
    ``now()`` and SQLite drops timezone info on read, so a round-trip check
    should assert metric identity, not the timestamp.

    ``volatility`` / ``beta`` / ``drawdown`` are the computed portfolio-level risk
    metrics (task P3-DB-3). They are optional — ``None`` when the cycle could not
    compute them — and are stored on this row rather than a separate table.
    """

    cycle_id: str
    total_value: decimal.Decimal
    cash: decimal.Decimal
    equity: decimal.Decimal
    buying_power: decimal.Decimal
    volatility: decimal.Decimal | None = None
    beta: decimal.Decimal | None = None
    drawdown: decimal.Decimal | None = None
    ts: _dt.datetime = dataclasses.field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc), compare=False
    )
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class PositionRecord:
    """One ``positions`` row, part of a :class:`PortfolioSnapshotRecord`.

    ``snapshot_id`` and ``id`` are assigned by
    :meth:`PortfolioSnapshotRepository.save_with_positions` — construct the
    record with just the market fields and let the repository bind it to the
    snapshot it writes.
    """

    symbol: str
    qty: decimal.Decimal
    avg_price: decimal.Decimal
    market_value: decimal.Decimal
    asset_class: str
    side: str
    snapshot_id: int | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class SnapshotWithPositions:
    """Result of :meth:`PortfolioSnapshotRepository.save_with_positions`."""

    snapshot: PortfolioSnapshotRecord
    positions: tuple[PositionRecord, ...]


class PortfolioSnapshotRepository:
    """CRUD-lite access to ``portfolio_snapshots`` (+ its ``positions``) over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_TABLE_NAME, MetaData(), autoload_with=engine)
        self._positions = Table(
            _POSITIONS_TABLE_NAME, MetaData(), autoload_with=engine
        )

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
                    volatility=record.volatility,
                    beta=record.beta,
                    drawdown=record.drawdown,
                )
            )
            new_id = int(result.inserted_primary_key[0])
        return dataclasses.replace(record, id=new_id)

    def save_with_positions(
        self,
        snapshot: PortfolioSnapshotRecord,
        positions: Sequence[PositionRecord],
    ) -> SnapshotWithPositions:
        """Persist ``snapshot`` and every row in ``positions`` in one transaction.

        Task P3-DB-2: the write each analysis pass performs. The snapshot row and
        all N position rows commit together or not at all — if any position row
        fails (e.g. a missing ``symbol``), the whole transaction rolls back and
        the snapshot never lands. Returns the saved snapshot and positions with
        their assigned ``id`` / ``snapshot_id``, positions in input order.
        """
        with self._engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")

            snap_id = int(
                conn.execute(
                    insert(self._table).values(
                        cycle_id=snapshot.cycle_id,
                        ts=snapshot.ts,
                        total_value=snapshot.total_value,
                        cash=snapshot.cash,
                        equity=snapshot.equity,
                        buying_power=snapshot.buying_power,
                        volatility=snapshot.volatility,
                        beta=snapshot.beta,
                        drawdown=snapshot.drawdown,
                    )
                ).inserted_primary_key[0]
            )

            saved_positions: list[PositionRecord] = []
            for pos in positions:
                pos_id = int(
                    conn.execute(
                        insert(self._positions).values(
                            snapshot_id=snap_id,
                            symbol=pos.symbol,
                            qty=pos.qty,
                            avg_price=pos.avg_price,
                            market_value=pos.market_value,
                            asset_class=pos.asset_class,
                            side=pos.side,
                        )
                    ).inserted_primary_key[0]
                )
                saved_positions.append(
                    dataclasses.replace(pos, snapshot_id=snap_id, id=pos_id)
                )

        return SnapshotWithPositions(
            snapshot=dataclasses.replace(snapshot, id=snap_id),
            positions=tuple(saved_positions),
        )

    def positions_for(self, snapshot_id: int) -> list[PositionRecord]:
        """Positions belonging to ``snapshot_id``, in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._positions)
                    .where(self._positions.c.snapshot_id == snapshot_id)
                    .order_by(self._positions.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [
            PositionRecord(
                symbol=row["symbol"],
                qty=row["qty"],
                avg_price=row["avg_price"],
                market_value=row["market_value"],
                asset_class=row["asset_class"],
                side=row["side"],
                snapshot_id=int(row["snapshot_id"]),
                id=int(row["id"]),
            )
            for row in rows
        ]

    def count_positions(self) -> int:
        """Number of rows currently in ``positions``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._positions)
                ).scalar_one()
            )

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
            volatility=row["volatility"],
            beta=row["beta"],
            drawdown=row["drawdown"],
            ts=row["ts"],
            id=int(row["id"]),
        )
