"""Synchronous ``strategy_hypotheses`` + ``strategy_decisions`` repositories — tasks P4-DB-1, P4-DB-2.

Phase 4's strategy layer produces, per cycle:

* **four hypotheses** — one per strategy family (protective put / put spread /
  collar / no-hedge). *All* are persisted, including the ones an agent rejected
  as ``NOT_VIABLE`` — the rejection reasoning is part of the decision trail
  (BRD §16). :class:`StrategyHypothesisRepository`.
* **one decision** — the Strategy Manager's reasoned selection over those
  hypotheses: the chosen hypothesis (or ``None`` for ``NO_TRADE``), the
  considered ``alternatives``, and the ``comparison`` table it reasoned over
  (BRD §18). :class:`StrategyDecisionRepository`.

The seam mirrors :class:`backend.db.agent_runs_repo.AgentRunRepository`: a plain
synchronous :class:`~sqlalchemy.engine.Engine`, each table reflected once at
construction, a small frozen record dataclass in and out. The API contracts
(:mod:`backend.models.strategy`) are deliberately *not* imported here — the
caller maps ``StrategyHypothesis`` / ``StrategyDecision`` onto these records, the
same way :mod:`backend.api.analyze` maps ``HedgeContext`` onto
``PortfolioSnapshotRecord``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any, Final

from sqlalchemy import MetaData, RowMapping, Table, func, insert, select
from sqlalchemy.engine import Engine

_HYPOTHESES_TABLE = "strategy_hypotheses"
_DECISIONS_TABLE = "strategy_decisions"

#: The ``hypothesis_verdict_enum`` values from migration ``0005_strategy_hypotheses``.
#: A ``NOT_VIABLE`` hypothesis is stored as ``REJECTED`` with a ``rejection_reason``.
HYPOTHESIS_VERDICTS: Final[frozenset[str]] = frozenset(
    {"ACCEPTED", "REJECTED", "MODIFIED", "NO_ACTION"}
)


@dataclasses.dataclass(frozen=True)
class StrategyHypothesisRecord:
    """One ``strategy_hypotheses`` row.

    ``id`` is assigned by the database on
    :meth:`StrategyHypothesisRepository.create` /
    :meth:`~StrategyHypothesisRepository.save_many`. ``verdict`` must be one of
    :data:`HYPOTHESIS_VERDICTS`; ``rejection_reason`` carries the "why" when the
    agent rejected its own family (``verdict == "REJECTED"``).
    """

    cycle_id: str
    strategy_type: str
    verdict: str
    legs: list[Any] | None = None
    metrics: dict[str, Any] | None = None
    rejection_reason: str | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class StrategyDecisionRecord:
    """One ``strategy_decisions`` row.

    ``selected_hypothesis_id`` is a nullable FK into ``strategy_hypotheses`` —
    ``None`` for a ``NO_TRADE`` decision. ``alternatives`` and ``comparison`` are
    JSON blobs (the considered hypotheses and the comparison table the manager
    reasoned over); both stay populated even when the decision is ``NO_TRADE``.
    """

    cycle_id: str
    action: str
    rationale: str
    selected_hypothesis_id: int | None = None
    alternatives: list[Any] | dict[str, Any] | None = None
    comparison: list[Any] | dict[str, Any] | None = None
    id: int | None = None


class StrategyHypothesisRepository:
    """CRUD-lite access to ``strategy_hypotheses`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_HYPOTHESES_TABLE, MetaData(), autoload_with=engine)

    def create(self, record: StrategyHypothesisRecord) -> StrategyHypothesisRecord:
        """Insert one hypothesis and return a copy carrying the assigned ``id``."""
        self._validate(record)
        with self._engine.begin() as conn:
            new_id = int(
                conn.execute(
                    insert(self._table).values(**self._values(record))
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(record, id=new_id)

    def save_many(
        self, records: Sequence[StrategyHypothesisRecord]
    ) -> tuple[StrategyHypothesisRecord, ...]:
        """Persist every hypothesis in ``records`` in one transaction.

        The Phase 4 write: all four hypotheses for a cycle commit together or not
        at all. Returns them in input order, each carrying its assigned ``id``.
        """
        for record in records:
            self._validate(record)
        saved: list[StrategyHypothesisRecord] = []
        with self._engine.begin() as conn:
            for record in records:
                new_id = int(
                    conn.execute(
                        insert(self._table).values(**self._values(record))
                    ).inserted_primary_key[0]
                )
                saved.append(dataclasses.replace(record, id=new_id))
        return tuple(saved)

    def get(self, hypothesis_id: int) -> StrategyHypothesisRecord | None:
        """Return the hypothesis with ``hypothesis_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(self._table).where(self._table.c.id == hypothesis_id)
                )
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def list_for_cycle(self, cycle_id: str) -> list[StrategyHypothesisRecord]:
        """Every hypothesis for ``cycle_id`` in insertion (``id``) order.

        Rejected / ``NOT_VIABLE`` hypotheses are included — the caller decides
        what to surface.
        """
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

    def list_all(self) -> list[StrategyHypothesisRecord]:
        """Every hypothesis across all cycles in insertion (``id``) order."""
        with self._engine.connect() as conn:
            rows = (
                conn.execute(select(self._table).order_by(self._table.c.id.asc()))
                .mappings()
                .all()
            )
        return [rec for rec in (self._to_record(r) for r in rows) if rec is not None]

    def count(self) -> int:
        """Number of rows currently in ``strategy_hypotheses``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._table)
                ).scalar_one()
            )

    @staticmethod
    def _validate(record: StrategyHypothesisRecord) -> None:
        if record.verdict not in HYPOTHESIS_VERDICTS:
            raise ValueError(
                f"verdict must be one of {sorted(HYPOTHESIS_VERDICTS)}, got {record.verdict!r}"
            )

    @staticmethod
    def _values(record: StrategyHypothesisRecord) -> dict[str, Any]:
        return {
            "cycle_id": record.cycle_id,
            "strategy_type": record.strategy_type,
            "verdict": record.verdict,
            "legs": record.legs,
            "metrics": record.metrics,
            "rejection_reason": record.rejection_reason,
        }

    @staticmethod
    def _to_record(row: RowMapping | None) -> StrategyHypothesisRecord | None:
        if row is None:
            return None
        return StrategyHypothesisRecord(
            cycle_id=row["cycle_id"],
            strategy_type=row["strategy_type"],
            verdict=row["verdict"],
            legs=row["legs"],
            metrics=row["metrics"],
            rejection_reason=row["rejection_reason"],
            id=int(row["id"]),
        )


class StrategyDecisionRepository:
    """CRUD-lite access to ``strategy_decisions`` over a plain (sync) Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_DECISIONS_TABLE, MetaData(), autoload_with=engine)

    def create(self, record: StrategyDecisionRecord) -> StrategyDecisionRecord:
        """Insert the decision and return a copy carrying the assigned ``id``.

        ``selected_hypothesis_id``, when set, must reference an existing
        ``strategy_hypotheses`` row — the FK is enforced (``PRAGMA foreign_keys``
        is turned on for SQLite).
        """
        with self._engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
            new_id = int(
                conn.execute(
                    insert(self._table).values(
                        cycle_id=record.cycle_id,
                        action=record.action,
                        selected_hypothesis_id=record.selected_hypothesis_id,
                        rationale=record.rationale,
                        alternatives=record.alternatives,
                        comparison=record.comparison,
                    )
                ).inserted_primary_key[0]
            )
        return dataclasses.replace(record, id=new_id)

    def get(self, decision_id: int) -> StrategyDecisionRecord | None:
        """Return the decision with ``decision_id``, or ``None`` if absent."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(self._table).where(self._table.c.id == decision_id)
                )
                .mappings()
                .one_or_none()
            )
        return self._to_record(row)

    def for_cycle(self, cycle_id: str) -> StrategyDecisionRecord | None:
        """The decision recorded for ``cycle_id`` (most recent ``id`` wins).

        One cycle normally produces exactly one decision; if a cycle were
        re-evaluated the latest row is the live one.
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

    def latest(self) -> StrategyDecisionRecord | None:
        """The most recently inserted decision across all cycles."""
        with self._engine.connect() as conn:
            row = (
                conn.execute(select(self._table).order_by(self._table.c.id.desc()))
                .mappings()
                .first()
            )
        return self._to_record(row)

    def count(self) -> int:
        """Number of rows currently in ``strategy_decisions``."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count()).select_from(self._table)
                ).scalar_one()
            )

    @staticmethod
    def _to_record(row: RowMapping | None) -> StrategyDecisionRecord | None:
        if row is None:
            return None
        selected = row["selected_hypothesis_id"]
        return StrategyDecisionRecord(
            cycle_id=row["cycle_id"],
            action=row["action"],
            rationale=row["rationale"],
            selected_hypothesis_id=None if selected is None else int(selected),
            alternatives=row["alternatives"],
            comparison=row["comparison"],
            id=int(row["id"]),
        )
