"""Synchronous ``execution_failures`` repository — task P5-DB-3.

An execution attempt that never reaches a fill still has to be auditable: a
pre-flight abort (stale quote, drifted price), a rejected broker submit, a leg
that timed out. Each writes one ``execution_failures`` row rather than a
misleading ``orders`` / ``fills`` record.

Same seam as :class:`backend.db.orders_repo.OrderRepository`: a plain
synchronous :class:`~sqlalchemy.engine.Engine`, the table reflected once at
construction, a frozen record dataclass in and out.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from typing import Any

from sqlalchemy import RowMapping, func, insert, select
from sqlalchemy.engine import Engine

from backend.db.table_cache import get_table

_TABLE_NAME = "execution_failures"


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@dataclasses.dataclass(frozen=True)
class ExecutionFailureRecord:
    """One ``execution_failures`` row.

    ``id`` is assigned by the database on
    :meth:`ExecutionFailureRepository.create`. ``order_id`` is ``None`` for a
    failure that happened before any order was created (a pre-flight abort);
    ``leg_symbol`` is ``None`` for an order-level failure. ``stage`` is a coarse
    tag — ``PREFLIGHT`` / ``SUBMIT`` / ``FILL``. ``detail`` is an optional JSON
    blob with the structured context. ``failed_at`` is excluded from equality —
    the column carries a ``server_default`` of ``now()``.
    """

    cycle_id: str
    stage: str
    reason: str
    order_id: int | None = None
    leg_symbol: str | None = None
    detail: dict[str, Any] | None = None
    failed_at: _dt.datetime = dataclasses.field(
        default_factory=_utcnow, compare=False
    )
    id: int | None = None


class ExecutionFailureRepository:
    """CRUD-lite access to ``execution_failures`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = get_table(engine, _TABLE_NAME)

    def create(self, record: ExecutionFailureRecord) -> ExecutionFailureRecord:
        """Insert one failure row and return a copy carrying the ``id``."""
        if not record.reason or not record.reason.strip():
            raise ValueError("an execution_failures row must carry a reason")
        with self._engine.begin() as conn:
            new_id = int(
                conn.execute(
                    insert(self._table).values(
                        cycle_id=record.cycle_id,
                        order_id=record.order_id,
                        leg_symbol=record.leg_symbol,
                        stage=record.stage,
                        reason=record.reason,
                        detail=record.detail,
                        failed_at=record.failed_at,
                    )
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(record, id=new_id)

    def get(self, failure_id: int) -> ExecutionFailureRecord | None:
        """Return the failure with ``failure_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._table).where(self._table.c.id == failure_id))
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def list_for_cycle(self, cycle_id: str) -> list[ExecutionFailureRecord]:
        """Every failure for ``cycle_id`` in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._table)
                    .where(self._table.c.cycle_id == cycle_id)
                    .order_by(self._table.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(r) for r in rows) if rec is not None]

    def list_all(self) -> list[ExecutionFailureRecord]:
        """Every failure across all cycles in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(select(self._table).order_by(self._table.c.id.asc()))
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(r) for r in rows) if rec is not None]

    def count(self) -> int:
        """Number of rows currently in ``execution_failures``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._table)
                ).scalar_one()
            )

    @staticmethod
    def _to_record(row: RowMapping | None) -> ExecutionFailureRecord | None:
        if row is None:
            return None
        order_id = row["order_id"]
        return ExecutionFailureRecord(
            cycle_id=row["cycle_id"],
            stage=row["stage"],
            reason=row["reason"],
            order_id=None if order_id is None else int(order_id),
            leg_symbol=row["leg_symbol"],
            detail=row["detail"],
            failed_at=row["failed_at"],
            id=int(row["id"]),
        )
