"""Synchronous ``risk_checks`` repository — task P5-DB-1.

Phase 5's risk gate produces exactly one ``risk_checks`` row per risk evaluation:
the Risk Agent's verdict (``APPROVE`` / ``MODIFY`` / ``REJECT``) over an approved
strategy, the full deterministic ``checks`` list it reasoned over, and the
``violations`` / ``warnings`` / ``modifications`` that back the verdict (BRD §20).

The verdict invariants mirror :class:`backend.models.risk.RiskDecision`:

* ``REJECT`` must name at least one violation;
* ``MODIFY`` must carry at least one modification;
* ``APPROVE`` cannot carry a violation.

The repository enforces them before the row hits the database, so a malformed
decision can never be persisted.

The seam mirrors :class:`backend.db.strategy_repo.StrategyHypothesisRepository`: a
plain synchronous :class:`~sqlalchemy.engine.Engine`, the table reflected once at
construction, a small frozen record dataclass in and out. The API contract
(:mod:`backend.models.risk`) is deliberately *not* imported here — the caller
maps ``RiskDecision`` onto :class:`RiskCheckRecord`.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final

from sqlalchemy import RowMapping, func, insert, select
from sqlalchemy.engine import Engine

from backend.db.table_cache import get_table

_TABLE_NAME = "risk_checks"

#: The Risk Agent verdicts (``backend.models.enums.RiskVerdict``). ``verdict`` is
#: a bare ``String(32)`` in migration ``0007_risk_checks`` — the repository is
#: what keeps it on-enum.
RISK_VERDICTS: Final[frozenset[str]] = frozenset({"APPROVE", "MODIFY", "REJECT"})


@dataclasses.dataclass(frozen=True)
class RiskCheckRecord:
    """One ``risk_checks`` row.

    ``id`` is assigned by the database on :meth:`RiskCheckRepository.create`.
    ``verdict`` must be one of :data:`RISK_VERDICTS`. ``checks`` /
    ``violations`` / ``warnings`` / ``modifications`` are JSON blobs — the
    deterministic checklist and the reasons behind the verdict. ``violations``
    is a list of strings; ``modifications`` a list of adjustment objects.
    """

    cycle_id: str
    verdict: str
    checks: list[Any] | None = None
    violations: list[Any] | None = None
    warnings: list[Any] | None = None
    modifications: list[Any] | None = None
    id: int | None = None


class RiskCheckRepository:
    """CRUD-lite access to ``risk_checks`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = get_table(engine, _TABLE_NAME)

    def create(self, record: RiskCheckRecord) -> RiskCheckRecord:
        """Insert one risk evaluation and return a copy carrying the ``id``."""
        self._validate(record)
        with self._engine.begin() as conn:
            new_id = int(
                conn.execute(
                    insert(self._table).values(**self._values(record))
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(record, id=new_id)

    def get(self, check_id: int) -> RiskCheckRecord | None:
        """Return the risk check with ``check_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._table).where(self._table.c.id == check_id))
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def for_cycle(self, cycle_id: str) -> RiskCheckRecord | None:
        """The risk check recorded for ``cycle_id`` (latest ``id`` wins).

        A cycle normally produces exactly one risk evaluation; a re-run makes
        the newest row the live one.
        """
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(self._table)
                    .where(self._table.c.cycle_id == cycle_id)
                    .order_by(self._table.c.id.desc())
                )
                .mappings()
                .first()
            )
        return self._to_record(row)

    def list_for_cycle(self, cycle_id: str) -> list[RiskCheckRecord]:
        """Every risk check for ``cycle_id`` in insertion (``id``) order."""
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

    def list_all(self) -> list[RiskCheckRecord]:
        """Every risk check across all cycles in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(select(self._table).order_by(self._table.c.id.asc()))
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(r) for r in rows) if rec is not None]

    def count(self) -> int:
        """Number of rows currently in ``risk_checks``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._table)
                ).scalar_one()
            )

    @staticmethod
    def _validate(record: RiskCheckRecord) -> None:
        if record.verdict not in RISK_VERDICTS:
            raise ValueError(
                f"verdict must be one of {sorted(RISK_VERDICTS)}, got {record.verdict!r}"
            )
        if record.verdict == "REJECT" and not record.violations:
            raise ValueError("a REJECT risk check must list at least one violation")
        if record.verdict == "MODIFY" and not record.modifications:
            raise ValueError("a MODIFY risk check must carry at least one modification")
        if record.verdict == "APPROVE" and record.violations:
            raise ValueError("an APPROVE risk check cannot carry violations")

    @staticmethod
    def _values(record: RiskCheckRecord) -> dict[str, Any]:
        return {
            "cycle_id": record.cycle_id,
            "verdict": record.verdict,
            "checks": record.checks,
            "violations": record.violations,
            "warnings": record.warnings,
            "modifications": record.modifications,
        }

    @staticmethod
    def _to_record(row: RowMapping | None) -> RiskCheckRecord | None:
        if row is None:
            return None
        return RiskCheckRecord(
            cycle_id=row["cycle_id"],
            verdict=row["verdict"],
            checks=row["checks"],
            violations=row["violations"],
            warnings=row["warnings"],
            modifications=row["modifications"],
            id=int(row["id"]),
        )
