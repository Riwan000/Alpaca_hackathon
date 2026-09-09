"""Monitoring repositories — tasks P7-DB-1, P7-DB-2, P7-DB-3, P7-DB-4.

Handles persistence and readback for:
1. Monitoring events (Level-1 deterministic triggers)
2. Reassessment events (Level-2 intelligent evaluations)
3. Hedge changes (before/after hedge ratios and delta adjustments)
4. Monitoring state (current vs target hedge, cooldown, active status)
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
from typing import Any

from sqlalchemy import desc, insert, select
from sqlalchemy.engine import Engine

from backend.db.table_cache import get_table
from backend.models.enums import HedgeAction, TriggerType

_MONITORING_EVENTS_TABLE = "monitoring_events"
_REASSESSMENT_EVENTS_TABLE = "reassessment_events"
_HEDGE_CHANGES_TABLE = "hedge_changes"
_MONITORING_STATE_TABLE = "monitoring_state"


@dataclasses.dataclass(frozen=True)
class MonitoringEventRecord:
    cycle_id: str
    trigger_type: str | TriggerType
    observed: dict[str, Any] | None = None
    threshold: decimal.Decimal | None = None
    fired_at: _dt.datetime | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class ReassessmentEventRecord:
    cycle_id: str
    outcome: str | HedgeAction
    reason: str
    trigger_event_id: int | None = None
    context: dict[str, Any] | None = None
    created_at: _dt.datetime | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class HedgeChangeRecord:
    cycle_id: str
    before_hedge_ratio: decimal.Decimal
    after_hedge_ratio: decimal.Decimal
    delta: decimal.Decimal
    action: str | HedgeAction
    reason: str
    reassessment_id: int | None = None
    detail: dict[str, Any] | None = None
    created_at: _dt.datetime | None = None
    id: int | None = None


@dataclasses.dataclass(frozen=True)
class MonitoringStateRecord:
    current_hedge: decimal.Decimal
    target_hedge: decimal.Decimal
    cooldown_until: _dt.datetime | None = None
    trigger_history: list[Any] = dataclasses.field(default_factory=list)
    monitoring_status: str = "ACTIVE"
    cycle_id: str | None = None
    detail: dict[str, Any] | None = None
    updated_at: _dt.datetime | None = None
    id: int | None = None


class MonitoringRepository:
    """Synchronous repository covering all Phase 7 monitoring tables."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._events = get_table(engine, _MONITORING_EVENTS_TABLE)
        self._reassessments = get_table(engine, _REASSESSMENT_EVENTS_TABLE)
        self._changes = get_table(engine, _HEDGE_CHANGES_TABLE)
        self._state = get_table(engine, _MONITORING_STATE_TABLE)

    # 1. Monitoring Events (P7-DB-1)
    def record_event(self, record: MonitoringEventRecord) -> MonitoringEventRecord:
        trigger_str = (
            record.trigger_type.value
            if isinstance(record.trigger_type, TriggerType)
            else str(record.trigger_type)
        )
        fired_at = record.fired_at or _dt.datetime.now(_dt.timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._events).values(
                    cycle_id=record.cycle_id,
                    trigger_type=trigger_str,
                    observed=record.observed,
                    threshold=record.threshold,
                    fired_at=fired_at,
                )
            )
            event_id = int(result.inserted_primary_key[0])

        return dataclasses.replace(record, id=event_id, fired_at=fired_at, trigger_type=trigger_str)

    def list_events(self, cycle_id: str | None = None) -> list[MonitoringEventRecord]:
        query = select(self._events)
        if cycle_id is not None:
            query = query.where(self._events.c.cycle_id == cycle_id)
        query = query.order_by(self._events.c.fired_at.asc())

        with self._engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        return [
            MonitoringEventRecord(
                id=r["id"],
                cycle_id=r["cycle_id"],
                trigger_type=r["trigger_type"],
                observed=r["observed"],
                threshold=r["threshold"],
                fired_at=r["fired_at"],
            )
            for r in rows
        ]

    # 2. Reassessment Events (P7-DB-2)
    def record_reassessment(self, record: ReassessmentEventRecord) -> ReassessmentEventRecord:
        outcome_str = (
            record.outcome.value
            if isinstance(record.outcome, HedgeAction)
            else str(record.outcome)
        )
        created_at = record.created_at or _dt.datetime.now(_dt.timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._reassessments).values(
                    cycle_id=record.cycle_id,
                    trigger_event_id=record.trigger_event_id,
                    outcome=outcome_str,
                    reason=record.reason,
                    context=record.context,
                    created_at=created_at,
                )
            )
            reassessment_id = int(result.inserted_primary_key[0])

        return dataclasses.replace(
            record, id=reassessment_id, created_at=created_at, outcome=outcome_str
        )

    def list_reassessments(self, cycle_id: str | None = None) -> list[ReassessmentEventRecord]:
        query = select(self._reassessments)
        if cycle_id is not None:
            query = query.where(self._reassessments.c.cycle_id == cycle_id)
        query = query.order_by(self._reassessments.c.created_at.asc())

        with self._engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        return [
            ReassessmentEventRecord(
                id=r["id"],
                cycle_id=r["cycle_id"],
                trigger_event_id=r["trigger_event_id"],
                outcome=r["outcome"],
                reason=r["reason"],
                context=r["context"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # 3. Hedge Changes (P7-DB-3)
    def record_hedge_change(self, record: HedgeChangeRecord) -> HedgeChangeRecord:
        action_str = (
            record.action.value
            if isinstance(record.action, HedgeAction)
            else str(record.action)
        )
        created_at = record.created_at or _dt.datetime.now(_dt.timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._changes).values(
                    cycle_id=record.cycle_id,
                    reassessment_id=record.reassessment_id,
                    before_hedge_ratio=record.before_hedge_ratio,
                    after_hedge_ratio=record.after_hedge_ratio,
                    delta=record.delta,
                    action=action_str,
                    reason=record.reason,
                    detail=record.detail,
                    created_at=created_at,
                )
            )
            change_id = int(result.inserted_primary_key[0])

        return dataclasses.replace(record, id=change_id, created_at=created_at, action=action_str)

    def list_hedge_changes(self, cycle_id: str | None = None) -> list[HedgeChangeRecord]:
        query = select(self._changes)
        if cycle_id is not None:
            query = query.where(self._changes.c.cycle_id == cycle_id)
        query = query.order_by(self._changes.c.created_at.asc())

        with self._engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        return [
            HedgeChangeRecord(
                id=r["id"],
                cycle_id=r["cycle_id"],
                reassessment_id=r["reassessment_id"],
                before_hedge_ratio=r["before_hedge_ratio"],
                after_hedge_ratio=r["after_hedge_ratio"],
                delta=r["delta"],
                action=r["action"],
                reason=r["reason"],
                detail=r["detail"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # 4. Monitoring State (P7-DB-4)
    def save_state(self, record: MonitoringStateRecord) -> MonitoringStateRecord:
        now = _dt.datetime.now(_dt.timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._state).values(
                    cycle_id=record.cycle_id,
                    current_hedge=record.current_hedge,
                    target_hedge=record.target_hedge,
                    cooldown_until=record.cooldown_until,
                    trigger_history=record.trigger_history,
                    monitoring_status=record.monitoring_status,
                    detail=record.detail,
                    updated_at=now,
                )
            )
            state_id = int(result.inserted_primary_key[0])

        return dataclasses.replace(record, id=state_id, updated_at=now)

    def get_latest_state(self) -> MonitoringStateRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._state).order_by(desc(self._state.c.id)).limit(1)
            ).mappings().first()

        if not row:
            return None

        return MonitoringStateRecord(
            id=row["id"],
            cycle_id=row["cycle_id"],
            current_hedge=row["current_hedge"],
            target_hedge=row["target_hedge"],
            cooldown_until=row["cooldown_until"],
            trigger_history=row["trigger_history"] or [],
            monitoring_status=row["monitoring_status"],
            detail=row["detail"],
            updated_at=row["updated_at"],
        )
