"""Synchronous ``orders`` + ``fills`` repository — tasks P5-DB-2, P5-DB-3.

Phase 5 execution persists, per submitted hedge:

* **one ``orders`` row** — the multi-leg combo order: its ``legs`` blob, the
  broker order id once Alpaca accepts it, and a ``status`` that only ever moves
  *forward* through the lifecycle (``PENDING → SUBMITTED → PARTIALLY_FILLED →
  FILLED``, or a terminal ``CANCELLED`` / ``EXPIRED`` / ``REJECTED``).
* **N ``fills`` rows** — one per leg that filled, each linked to the order by
  ``order_id`` (FK, ``ON DELETE CASCADE``), carrying the realized ``price`` and
  the ``slippage`` versus the price the plan expected
  (:meth:`OrderRepository.record_fill`, ``slippage = price - expected_price``).

The seam mirrors :class:`backend.db.repository.PortfolioSnapshotRepository`: a
plain synchronous :class:`~sqlalchemy.engine.Engine`, each table reflected once
at construction, small frozen record dataclasses in and out.
:meth:`OrderRepository.save_with_fills` writes the order and its fills in one
transaction — a bad fill row rolls the order back with it.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
from collections.abc import Sequence
from typing import Any, Final

from sqlalchemy import RowMapping, func, insert, select, update
from sqlalchemy.engine import Engine

from backend.db.table_cache import get_table

_ORDERS_TABLE = "orders"
_FILLS_TABLE = "fills"

#: ``order_status_enum`` values (migration ``0008_orders`` /
#: ``backend.models.enums.OrderStatus``), ranked by lifecycle progress. A status
#: transition is monotonic iff the rank never decreases.
_STATUS_RANK: Final[dict[str, int]] = {
    "PENDING": 0,
    "SUBMITTED": 1,
    "PARTIALLY_FILLED": 2,
    "FILLED": 3,
    "CANCELLED": 3,
    "EXPIRED": 3,
    "REJECTED": 3,
}

#: Once an order reaches one of these it is done — no further transition (except
#: a no-op to the same status) is allowed.
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"FILLED", "CANCELLED", "EXPIRED", "REJECTED"}
)

ORDER_STATUSES: Final[frozenset[str]] = frozenset(_STATUS_RANK)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class MonotonicStatusError(ValueError):
    """Raised when an ``orders.status`` update would move the lifecycle backward."""


@dataclasses.dataclass(frozen=True)
class OrderRecord:
    """One ``orders`` row.

    ``id`` is assigned by the database on :meth:`OrderRepository.create`.
    ``order_class`` maps to the reserved-word ``class`` column (``MLEG`` /
    ``COMBO`` / ``SINGLE``). ``status`` must be one of :data:`ORDER_STATUSES` and
    only moves forward through the lifecycle. ``broker_order_id`` is ``None``
    until Alpaca accepts the order (the column is unique-nullable, so several
    not-yet-submitted orders can coexist). ``submitted_at`` is excluded from
    equality — the column carries a ``server_default`` of ``now()`` and SQLite
    drops timezone info on read.
    """

    cycle_id: str
    order_class: str
    status: str = "PENDING"
    legs: list[Any] | None = None
    broker_order_id: str | None = None
    submitted_at: _dt.datetime = dataclasses.field(
        default_factory=_utcnow, compare=False
    )
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class FillRecord:
    """One ``fills`` row, part of an :class:`OrderRecord`.

    ``order_id`` links to the parent order. ``slippage`` is the realized
    ``price`` minus the price the execution plan expected for the leg — ``None``
    when no expected price was supplied. ``filled_at`` is excluded from equality
    for the same reason as :attr:`OrderRecord.submitted_at`.
    """

    order_id: int
    leg_symbol: str
    qty: decimal.Decimal
    price: decimal.Decimal
    slippage: decimal.Decimal | None = None
    filled_at: _dt.datetime = dataclasses.field(
        default_factory=_utcnow, compare=False
    )
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class OrderWithFills:
    """An order and its fills, in insertion order — see :meth:`OrderRepository.get_with_fills`."""

    order: OrderRecord
    fills: tuple[FillRecord, ...]


def _to_decimal(value: decimal.Decimal | int | float | str) -> decimal.Decimal:
    return value if isinstance(value, decimal.Decimal) else decimal.Decimal(str(value))


class OrderRepository:
    """CRUD-lite access to ``orders`` (+ its ``fills``) over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._orders = get_table(engine, _ORDERS_TABLE)
        self._fills = get_table(engine, _FILLS_TABLE)

    # -- writes -------------------------------------------------------------- #

    def create(self, order: OrderRecord) -> OrderRecord:
        """Insert ``order`` and return a copy carrying the assigned ``id``."""
        self._validate_status(order.status)
        with self._engine.begin() as conn:
            new_id = int(
                conn.execute(
                    insert(self._orders).values(**self._order_values(order))
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(order, id=new_id)

    def save_with_fills(
        self, order: OrderRecord, fills: Sequence[FillRecord]
    ) -> OrderWithFills:
        """Persist ``order`` and every row in ``fills`` in one transaction.

        The order row and all N fill rows commit together or not at all — if any
        fill row fails, the whole transaction rolls back and the order never
        lands. ``fills`` are bound to the new order's ``id``; any ``order_id``
        already on a passed :class:`FillRecord` is overridden.
        """
        self._validate_status(order.status)
        with self._engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")

            order_id = int(
                conn.execute(
                    insert(self._orders).values(**self._order_values(order))
                ).inserted_primary_key[0]
            )

            saved_fills: list[FillRecord] = []
            for fill in fills:
                bound = dataclasses.replace(fill, order_id=order_id)
                fill_id = int(
                    conn.execute(
                        insert(self._fills).values(**self._fill_values(bound))
                    ).inserted_primary_key[0]
                )
                saved_fills.append(dataclasses.replace(bound, id=fill_id))

        return OrderWithFills(
            order=dataclasses.replace(order, id=order_id),
            fills=tuple(saved_fills),
        )

    def add_fill(self, fill: FillRecord) -> FillRecord:
        """Insert one fill for an existing order and return it with its ``id``."""
        if self.get(fill.order_id) is None:
            raise LookupError(f"orders row {fill.order_id} does not exist")
        with self._engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
            fill_id = int(
                conn.execute(
                    insert(self._fills).values(**self._fill_values(fill))
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(fill, id=fill_id)

    def record_fill(
        self,
        order_id: int,
        *,
        leg_symbol: str,
        qty: decimal.Decimal | int | float | str,
        price: decimal.Decimal | int | float | str,
        expected_price: decimal.Decimal | int | float | str | None = None,
    ) -> FillRecord:
        """Insert a fill, computing ``slippage = price - expected_price`` (P5-DB-3).

        When ``expected_price`` is omitted the fill is stored with a ``NULL``
        slippage.
        """
        realized = _to_decimal(price)
        slippage = (
            None if expected_price is None else realized - _to_decimal(expected_price)
        )
        return self.add_fill(
            FillRecord(
                order_id=order_id,
                leg_symbol=leg_symbol,
                qty=_to_decimal(qty),
                price=realized,
                slippage=slippage,
            )
        )

    def update_status(self, order_id: int, new_status: str) -> OrderRecord:
        """Advance ``order_id`` to ``new_status`` and return the updated record.

        Raises :class:`MonotonicStatusError` if the transition would move the
        lifecycle backward (rank decrease) or leave a terminal state.
        """
        self._validate_status(new_status)
        current = self.get(order_id)
        if current is None:
            raise LookupError(f"orders row {order_id} does not exist")

        if new_status != current.status:
            if current.status in _TERMINAL_STATUSES:
                raise MonotonicStatusError(
                    f"order {order_id} is terminal at {current.status!r}; "
                    f"cannot move to {new_status!r}"
                )
            if _STATUS_RANK[new_status] < _STATUS_RANK[current.status]:
                raise MonotonicStatusError(
                    f"order {order_id}: {current.status!r} -> {new_status!r} "
                    "is not a monotonic status transition"
                )

        with self._engine.begin() as conn:
            conn.execute(
                update(self._orders)
                .where(self._orders.c.id == order_id)
                .values(status=new_status)
            )
        updated = self.get(order_id)
        assert updated is not None  # just confirmed it exists, inside one process
        return updated

    def set_broker_order_id(self, order_id: int, broker_order_id: str) -> OrderRecord:
        """Stamp the broker's order id once Alpaca accepts the order."""
        if self.get(order_id) is None:
            raise LookupError(f"orders row {order_id} does not exist")
        with self._engine.begin() as conn:
            conn.execute(
                update(self._orders)
                .where(self._orders.c.id == order_id)
                .values(broker_order_id=broker_order_id)
            )
        updated = self.get(order_id)
        assert updated is not None
        return updated

    # -- reads ------------------------------------------------------------- #

    def get(self, order_id: int) -> OrderRecord | None:
        """Return the order with ``order_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._orders).where(self._orders.c.id == order_id))
                .mappings()
                .one_or_none()
            )
        return self._to_order(row)

    def get_with_fills(self, order_id: int) -> OrderWithFills | None:
        """Return the order plus its fills (insertion order), or ``None``."""
        order = self.get(order_id)
        if order is None or order.id is None:
            return None
        return OrderWithFills(order=order, fills=tuple(self.fills_for(order.id)))

    def fills_for(self, order_id: int) -> list[FillRecord]:
        """Fills belonging to ``order_id``, in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._fills)
                    .where(self._fills.c.order_id == order_id)
                    .order_by(self._fills.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [self._to_fill(r) for r in rows]

    def list_for_cycle(self, cycle_id: str) -> list[OrderRecord]:
        """Every order for ``cycle_id`` in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._orders)
                    .where(self._orders.c.cycle_id == cycle_id)
                    .order_by(self._orders.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [o for o in (self._to_order(r) for r in rows) if o is not None]

    def list_all(self) -> list[OrderRecord]:
        """Every order across all cycles in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(select(self._orders).order_by(self._orders.c.id.asc()))
                .mappings()
                .all()
            )
        return [o for o in (self._to_order(r) for r in rows) if o is not None]

    def count(self) -> int:
        """Number of rows currently in ``orders``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._orders)
                ).scalar_one()
            )

    def count_fills(self) -> int:
        """Number of rows currently in ``fills``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._fills)
                ).scalar_one()
            )

    # -- helpers --------------------------------------------------------- #

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in ORDER_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(ORDER_STATUSES)}, got {status!r}"
            )

    @staticmethod
    def _order_values(order: OrderRecord) -> dict[str, Any]:
        return {
            "cycle_id": order.cycle_id,
            "broker_order_id": order.broker_order_id,
            "class": order.order_class,
            "legs": order.legs,
            "status": order.status,
            "submitted_at": order.submitted_at,
        }

    @staticmethod
    def _fill_values(fill: FillRecord) -> dict[str, Any]:
        return {
            "order_id": fill.order_id,
            "leg_symbol": fill.leg_symbol,
            "qty": fill.qty,
            "price": fill.price,
            "slippage": fill.slippage,
            "filled_at": fill.filled_at,
        }

    @staticmethod
    def _to_order(row: RowMapping | None) -> OrderRecord | None:
        if row is None:
            return None
        return OrderRecord(
            cycle_id=row["cycle_id"],
            order_class=row["class"],
            status=row["status"],
            legs=row["legs"],
            broker_order_id=row["broker_order_id"],
            submitted_at=row["submitted_at"],
            id=int(row["id"]),
        )

    @staticmethod
    def _to_fill(row: RowMapping) -> FillRecord:
        return FillRecord(
            order_id=int(row["order_id"]),
            leg_symbol=row["leg_symbol"],
            qty=row["qty"],
            price=row["price"],
            slippage=row["slippage"],
            filled_at=row["filled_at"],
            id=int(row["id"]),
        )
