"""Synchronous ``agent_runs`` repository — task P3-DB-1.

Every analysis pass fans one ``cycle_id`` out across the market / news / options /
risk agents. Each agent's execution is a single ``agent_runs`` row:

* :meth:`AgentRunRepository.create` writes the row when the agent starts
  (``started_at`` set, ``outputs`` / ``error`` / ``duration_ms`` still ``NULL``).
* :meth:`AgentRunRepository.finish` closes it when the agent returns — with
  ``outputs`` on success, or ``error`` on failure — and stamps ``duration_ms``
  (measured by the caller) and ``finished_at``.

The timeline read — "a row per agent, in start order, each with a duration" — is
what P3-DB-4's ``GET /agent-runs?cycle_id=`` will serve; see
:meth:`AgentRunRepository.list_for_cycle`.

The seam is deliberately sync and mirrors
:class:`backend.db.repository.PortfolioSnapshotRepository`: a plain
:class:`~sqlalchemy.engine.Engine`, table reflected once at construction, small
frozen record dataclass in and out.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from typing import Any

from sqlalchemy import MetaData, RowMapping, Table, func, insert, select, update
from sqlalchemy.engine import Engine

_TABLE_NAME = "agent_runs"


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@dataclasses.dataclass(frozen=True)
class AgentRunRecord:
    """One ``agent_runs`` row.

    ``id`` is assigned by the database on :meth:`AgentRunRepository.create`.
    ``started_at`` and ``finished_at`` are excluded from equality: the column
    carries a ``server_default`` of ``now()`` and SQLite drops timezone info on
    read, so a round-trip check should assert payload identity (``outputs`` /
    ``error`` / ``duration_ms``), not wall-clock timestamps.
    """

    cycle_id: str
    agent_name: str
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
    started_at: _dt.datetime = dataclasses.field(
        default_factory=_utcnow, compare=False
    )
    finished_at: _dt.datetime | None = dataclasses.field(default=None, compare=False)
    id: int | None = None


class AgentRunRepository:
    """CRUD-lite access to ``agent_runs`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_TABLE_NAME, MetaData(), autoload_with=engine)

    def create(self, record: AgentRunRecord) -> AgentRunRecord:
        """Insert a *started* run and return a copy carrying the assigned ``id``.

        Only the start-of-run columns are written; ``outputs`` / ``error`` /
        ``duration_ms`` / ``finished_at`` stay ``NULL`` until :meth:`finish`.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._table).values(
                    cycle_id=record.cycle_id,
                    agent_name=record.agent_name,
                    inputs=record.inputs,
                    outputs=None,
                    error=None,
                    started_at=record.started_at,
                    finished_at=None,
                    duration_ms=None,
                )
            )
            new_id = int(result.inserted_primary_key[0])
        return dataclasses.replace(
            record,
            id=new_id,
            outputs=None,
            error=None,
            duration_ms=None,
            finished_at=None,
        )

    def finish(
        self,
        run_id: int,
        *,
        duration_ms: int,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AgentRunRecord:
        """Close ``run_id`` and return the updated record.

        Pass exactly one of ``outputs`` (success) or ``error`` (failure):

        * success — ``outputs`` is stored, ``error`` stays ``NULL``;
        * failure — ``error`` is stored, ``outputs`` stays ``NULL``.

        Passing both, or neither, is a programming error. ``finished_at`` is
        stamped here; ``duration_ms`` is supplied by the caller (it owns the
        clock around the agent call).
        """
        if (outputs is None) == (error is None):
            raise ValueError(
                "finish() takes exactly one of `outputs` or `error`"
            )
        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

        if self.get(run_id) is None:
            raise LookupError(f"agent_runs row {run_id} does not exist")

        with self._engine.begin() as conn:
            conn.execute(
                update(self._table)
                .where(self._table.c.id == run_id)
                .values(
                    outputs=outputs,
                    error=error,
                    duration_ms=duration_ms,
                    finished_at=_utcnow(),
                )
            )
        updated = self.get(run_id)
        assert updated is not None  # just confirmed it exists, inside one process
        return updated

    def get(self, run_id: int) -> AgentRunRecord | None:
        """Return the run with ``run_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._table).where(self._table.c.id == run_id))
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def list_for_cycle(self, cycle_id: str) -> list[AgentRunRecord]:
        """All runs for ``cycle_id`` in start order (``id`` breaks ties)."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._table)
                    .where(self._table.c.cycle_id == cycle_id)
                    .order_by(
                        self._table.c.started_at.asc(), self._table.c.id.asc()
                    )
                )
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(row) for row in rows) if rec is not None]

    def list_all(self) -> list[AgentRunRecord]:
        """Every run across all cycles in start order (``id`` breaks ties).

        The unfiltered form of :meth:`list_for_cycle`, backing
        ``GET /agent-runs`` with no ``cycle_id`` (task P3-DB-4).
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    select(self._table).order_by(
                        self._table.c.started_at.asc(), self._table.c.id.asc()
                    )
                )
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(row) for row in rows) if rec is not None]

    def count(self) -> int:
        """Number of rows currently in ``agent_runs``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._table)
                ).scalar_one()
            )

    @staticmethod
    def _to_record(row: RowMapping | None) -> AgentRunRecord | None:
        if row is None:
            return None
        return AgentRunRecord(
            cycle_id=row["cycle_id"],
            agent_name=row["agent_name"],
            inputs=row["inputs"],
            outputs=row["outputs"],
            error=row["error"],
            duration_ms=row["duration_ms"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            id=int(row["id"]),
        )
