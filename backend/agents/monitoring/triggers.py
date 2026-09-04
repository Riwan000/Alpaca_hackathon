"""Trigger evaluators + deadband + cooldown — Tasks P7-BE-2..4 (BRD §25–§27).

Level-1 monitoring (``agent.py``) answers *"is any absolute threshold breached
right now?"*. This module answers the adjacent questions the adaptive loop needs
before it escalates to Level-2:

- **P7-BE-2** — six focused trigger evaluators: ``hedge_drift``,
  ``drawdown_change``, ``volatility_change``, ``event``, ``expiration`` and
  ``emergency``. Each returns a typed :class:`TriggerObservation` (its payload)
  or ``None``.
- **P7-BE-3** — :func:`apply_deadband` drops *deviation* triggers whose excess
  over the firing threshold sits inside a small band (sensor noise), so a hedge
  ratio nudged by less than the deadband raises nothing.
- **P7-BE-4** — :func:`apply_cooldown` suppresses normal triggers for a window
  after a hedge adjustment; a trigger with ``is_emergency=True`` bypasses it.

Nothing here trades or touches a broker — it only classifies observations.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.agents.monitoring.agent import MonitoringThresholds
from backend.models.enums import TriggerType
from backend.models.hedge_context import CurrentHedge, HedgeContext
from backend.models.monitoring import MonitoringState, TriggerObservation

__all__ = [
    "TriggerEngine",
    "apply_cooldown",
    "apply_deadband",
    "evaluate_drawdown_change",
    "evaluate_emergency",
    "evaluate_event",
    "evaluate_expiration",
    "evaluate_hedge_drift",
    "evaluate_triggers",
    "evaluate_volatility_change",
    "start_cooldown",
]

#: Trigger types produced from a continuous *deviation* signal — the only ones
#: the deadband filter reasons about. ``TIME_ELAPSED`` (a countdown) and
#: ``CORRELATION_BREAKDOWN`` (a categorical event) are passed through untouched.
_DEADBAND_TRIGGER_TYPES: frozenset[TriggerType] = frozenset(
    {
        TriggerType.PORTFOLIO_DELTA,
        TriggerType.DRAWDOWN_LIMIT,
        TriggerType.VOLATILITY_SPIKE,
    }
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resolved_hedge_ratios(context: HedgeContext) -> tuple[float, float]:
    """``(current, target)`` hedge ratio with the documented fallbacks applied."""
    current = context.current_hedge.hedge_ratio
    target = context.current_hedge.target_hedge_ratio
    if target is None:
        target = context.objective.target_hedge_ratio
    return (current or 0.0, target or 0.0)


def _earliest_expiration(hedge: CurrentHedge) -> date | None:
    """Nearest expiration across the hedge's own field and its option legs."""
    candidates: list[date] = []
    if hedge.expiration is not None:
        candidates.append(hedge.expiration)
    for leg in hedge.legs:
        exp = getattr(leg, "expiration", None)
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp).date()
        if isinstance(exp, date):
            candidates.append(exp)
    return min(candidates) if candidates else None


# --------------------------------------------------------------------------- #
# P7-BE-2 — Trigger evaluators
# --------------------------------------------------------------------------- #


def evaluate_hedge_drift(
    context: HedgeContext, thresholds: MonitoringThresholds | None = None
) -> TriggerObservation | None:
    """Hedge ratio has drifted from target by more than ``hedge_drift_pct``."""
    thr = thresholds or MonitoringThresholds()
    current, target = _resolved_hedge_ratios(context)
    drift = abs(current - target)
    if drift <= thr.hedge_drift_pct:
        return None
    return TriggerObservation(
        trigger_type=TriggerType.PORTFOLIO_DELTA,
        observed_at=context.timestamp,
        observed_value=round(drift, 4),
        threshold=round(thr.hedge_drift_pct, 4),
        detail=(
            f"Hedge drift {drift:.2%} (|current {current:.2f} - target {target:.2f}|) "
            f"exceeded {thr.hedge_drift_pct:.2%}"
        ),
        breached=True,
    )


def evaluate_drawdown_change(
    context: HedgeContext,
    previous_state: MonitoringState | None = None,
    thresholds: MonitoringThresholds | None = None,
) -> TriggerObservation | None:
    """Drawdown moved more than ``drawdown_change`` since the previous snapshot."""
    thr = thresholds or MonitoringThresholds()
    curr = context.portfolio_state.drawdown
    prev = previous_state.drawdown if previous_state is not None else None
    if curr is None or prev is None:
        return None
    change = abs(curr - prev)
    if change <= thr.drawdown_change:
        return None
    return TriggerObservation(
        trigger_type=TriggerType.DRAWDOWN_LIMIT,
        observed_at=context.timestamp,
        observed_value=round(change, 4),
        threshold=round(thr.drawdown_change, 4),
        detail=(
            f"Drawdown changed {change:.2%} ({prev:.2%} -> {curr:.2%}), "
            f"beyond {thr.drawdown_change:.2%}"
        ),
        breached=True,
    )


def evaluate_volatility_change(
    context: HedgeContext,
    previous_state: MonitoringState | None = None,
    thresholds: MonitoringThresholds | None = None,
) -> TriggerObservation | None:
    """Realized volatility moved more than ``volatility_change`` since last snapshot."""
    thr = thresholds or MonitoringThresholds()
    curr = context.portfolio_state.volatility
    prev = previous_state.volatility if previous_state is not None else None
    if curr is None or prev is None:
        return None
    change = abs(curr - prev)
    if change <= thr.volatility_change:
        return None
    return TriggerObservation(
        trigger_type=TriggerType.VOLATILITY_SPIKE,
        observed_at=context.timestamp,
        observed_value=round(change, 4),
        threshold=round(thr.volatility_change, 4),
        detail=(
            f"Volatility changed {change:.4f} ({prev:.4f} -> {curr:.4f}), "
            f"beyond {thr.volatility_change:.4f}"
        ),
        breached=True,
    )


def evaluate_event(
    context: HedgeContext, thresholds: MonitoringThresholds | None = None
) -> TriggerObservation | None:
    """A flagged market event or severely negative news item in the context."""
    thr = thresholds or MonitoringThresholds()
    for item in context.news_context:
        if item.is_event:
            return TriggerObservation(
                trigger_type=TriggerType.CORRELATION_BREAKDOWN,
                observed_at=context.timestamp,
                observed_value=item.sentiment,
                threshold=round(thr.news_sentiment_min, 4),
                detail=f"Major market event: {item.headline}",
                breached=True,
            )
        if item.sentiment is not None and item.sentiment <= thr.news_sentiment_min:
            return TriggerObservation(
                trigger_type=TriggerType.CORRELATION_BREAKDOWN,
                observed_at=context.timestamp,
                observed_value=round(item.sentiment, 4),
                threshold=round(thr.news_sentiment_min, 4),
                detail=f"Severe negative sentiment ({item.sentiment:.2f}): {item.headline}",
                breached=True,
            )
    return None


def evaluate_expiration(
    context: HedgeContext, thresholds: MonitoringThresholds | None = None
) -> TriggerObservation | None:
    """Active hedge is within ``days_to_expiration`` of its nearest expiry."""
    thr = thresholds or MonitoringThresholds()
    if not context.current_hedge.active:
        return None
    exp = _earliest_expiration(context.current_hedge)
    if exp is None:
        return None
    ctx_date = (
        context.timestamp.date()
        if isinstance(context.timestamp, datetime)
        else date.today()
    )
    days_to_exp = float((exp - ctx_date).days)
    if days_to_exp > thr.days_to_expiration:
        return None
    return TriggerObservation(
        trigger_type=TriggerType.TIME_ELAPSED,
        observed_at=context.timestamp,
        observed_value=round(days_to_exp, 2),
        threshold=round(thr.days_to_expiration, 2),
        detail=(
            f"Hedge expiry in {days_to_exp:.1f}d, at or under {thr.days_to_expiration:.1f}d"
        ),
        breached=True,
    )


def evaluate_emergency(
    context: HedgeContext, thresholds: MonitoringThresholds | None = None
) -> TriggerObservation | None:
    """A catastrophic breach that must bypass the cooldown window.

    Checked most-portfolio-critical first: deep drawdown, then a volatility
    blow-out (realized vol or VIX). Returns the single most severe observation.
    """
    thr = thresholds or MonitoringThresholds()

    drawdown = context.portfolio_state.drawdown
    if drawdown is not None and abs(drawdown) >= thr.emergency_drawdown:
        return TriggerObservation(
            trigger_type=TriggerType.DRAWDOWN_LIMIT,
            observed_at=context.timestamp,
            observed_value=round(abs(drawdown), 4),
            threshold=round(thr.emergency_drawdown, 4),
            detail=(
                f"EMERGENCY: drawdown {abs(drawdown):.2%} at or past "
                f"{thr.emergency_drawdown:.2%}"
            ),
            breached=True,
            is_emergency=True,
        )

    vol = context.portfolio_state.volatility
    vix = context.market_state.vix if context.market_state else None
    vol_hit = vol is not None and vol >= thr.emergency_volatility
    vix_hit = vix is not None and vix >= thr.emergency_vix
    if vol_hit or vix_hit:
        observed = vol if vol_hit else vix
        limit = thr.emergency_volatility if vol_hit else thr.emergency_vix
        return TriggerObservation(
            trigger_type=TriggerType.VOLATILITY_SPIKE,
            observed_at=context.timestamp,
            observed_value=round(observed, 4) if observed is not None else None,
            threshold=round(limit, 4),
            detail=(
                f"EMERGENCY: volatility blow-out (vol={vol}, vix={vix}) "
                f"past {limit}"
            ),
            breached=True,
            is_emergency=True,
        )
    return None


def evaluate_triggers(
    context: HedgeContext,
    previous_state: MonitoringState | None = None,
    thresholds: MonitoringThresholds | None = None,
) -> list[TriggerObservation]:
    """Run every evaluator and return the fired observations (emergency first)."""
    thr = thresholds or MonitoringThresholds()
    candidates = [
        evaluate_emergency(context, thr),
        evaluate_hedge_drift(context, thr),
        evaluate_drawdown_change(context, previous_state, thr),
        evaluate_volatility_change(context, previous_state, thr),
        evaluate_event(context, thr),
        evaluate_expiration(context, thr),
    ]
    return [obs for obs in candidates if obs is not None]


# --------------------------------------------------------------------------- #
# P7-BE-3 — Deadband filter
# --------------------------------------------------------------------------- #


def apply_deadband(
    triggers: list[TriggerObservation], deadband: float | None = None
) -> list[TriggerObservation]:
    """Drop deviation triggers whose excess over the threshold is within the band.

    A deviation of ``observed_value`` that clears its ``threshold`` by ``deadband``
    or less is treated as sensor noise and suppressed. Emergency triggers,
    countdown triggers (``TIME_ELAPSED``), categorical events
    (``CORRELATION_BREAKDOWN``) and any trigger missing a numeric pair pass
    through unchanged.
    """
    band = MonitoringThresholds().deadband if deadband is None else deadband
    kept: list[TriggerObservation] = []
    for obs in triggers:
        if (
            obs.is_emergency
            or obs.trigger_type not in _DEADBAND_TRIGGER_TYPES
            or obs.observed_value is None
            or obs.threshold is None
        ):
            kept.append(obs)
            continue
        excess = abs(obs.observed_value) - abs(obs.threshold)
        if excess > band:
            kept.append(obs)
    return kept


# --------------------------------------------------------------------------- #
# P7-BE-4 — Cooldown after an adjustment (emergency bypass)
# --------------------------------------------------------------------------- #


def start_cooldown(
    now: datetime | None = None,
    *,
    seconds: int | None = None,
    thresholds: MonitoringThresholds | None = None,
) -> datetime:
    """``cooldown_until`` timestamp to stamp on the state after a hedge adjustment."""
    base = now or datetime.now(timezone.utc)
    secs = (
        seconds
        if seconds is not None
        else (thresholds or MonitoringThresholds()).cooldown_seconds
    )
    return base + timedelta(seconds=secs)


def apply_cooldown(
    triggers: list[TriggerObservation],
    *,
    cooldown_until: datetime | None,
    now: datetime | None = None,
) -> list[TriggerObservation]:
    """Suppress normal triggers while the post-adjustment cooldown is active.

    Outside the window (``cooldown_until`` is ``None`` or already past) every
    trigger passes. Inside it, only ``is_emergency`` triggers survive.
    Timestamps are expected tz-aware (UTC).
    """
    if cooldown_until is None:
        return list(triggers)
    current = now or datetime.now(timezone.utc)
    if current >= cooldown_until:
        return list(triggers)
    return [obs for obs in triggers if obs.is_emergency]


# --------------------------------------------------------------------------- #
# Engine — evaluate -> deadband -> cooldown
# --------------------------------------------------------------------------- #


class TriggerEngine:
    """Compose the P7-BE-2..4 stages into one pass.

    ``evaluate`` runs the six evaluators, drops sub-threshold deviations via the
    deadband, then applies the cooldown gate (emergencies bypass it).
    """

    def __init__(self, thresholds: MonitoringThresholds | None = None) -> None:
        self.thresholds = thresholds or MonitoringThresholds()

    def evaluate(
        self,
        context: HedgeContext,
        *,
        previous_state: MonitoringState | None = None,
        cooldown_until: datetime | None = None,
        now: datetime | None = None,
    ) -> list[TriggerObservation]:
        raw = evaluate_triggers(context, previous_state, self.thresholds)
        filtered = apply_deadband(raw, self.thresholds.deadband)
        return apply_cooldown(filtered, cooldown_until=cooldown_until, now=now)
