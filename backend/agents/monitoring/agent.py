"""Monitoring Agent — Level 1 deterministic checks (Task P7-BE-1 / BRD §24–27).

The Monitoring Agent does NOT make trades and has no execution path.
Its sole responsibility is:
1. Detect whether the current portfolio / hedge has drifted or breached quantitative thresholds.
2. Run Level-1 deterministic checks across six categories:
   - Drawdown (DRAWDOWN_LIMIT)
   - Hedge drift (PORTFOLIO_DELTA)
   - Volatility spike / regime shock (VOLATILITY_SPIKE)
   - Gross exposure / leverage breach (PORTFOLIO_DELTA)
   - Expiration / time elapsed (TIME_ELAPSED)
   - Major state change / correlation breakdown / events (CORRELATION_BREAKDOWN)
3. Snapshot and optionally persist the rolling MonitoringState and MonitoringEvents.
"""

from __future__ import annotations

import dataclasses
import decimal
import logging
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from backend.config import Settings, get_settings
from backend.models.enums import TriggerType
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState, TriggerObservation

if TYPE_CHECKING:
    from backend.db.monitoring_repo import MonitoringRepository

__all__ = [
    "MonitoringAgent",
    "MonitoringThresholds",
    "evaluate_level1_checks",
]

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class MonitoringThresholds:
    """Quantitative thresholds for Level-1 deterministic monitoring checks.

    The first block is used by the absolute Level-1 checks in
    :class:`MonitoringAgent`. The ``*_change`` / ``emergency_*`` / ``deadband`` /
    ``cooldown_seconds`` block drives the trigger evaluator pipeline in
    :mod:`backend.agents.monitoring.triggers` (Tasks P7-BE-2..4).
    """

    drawdown_pct: float = 0.05
    hedge_drift_pct: float = 0.05
    volatility: float = 0.30
    vix: float = 30.0
    gross_exposure: float = 1.00
    days_to_expiration: float = 7.0
    beta_min: float = 0.0
    beta_max: float = 2.0
    news_sentiment_min: float = -0.60

    # --- Trigger evaluators: change deltas vs the previous snapshot --------- #
    drawdown_change: float = 0.03
    volatility_change: float = 0.10

    # --- Emergency escalation levels (bypass the cooldown window) ---------- #
    emergency_drawdown: float = 0.15
    emergency_volatility: float = 0.60
    emergency_vix: float = 45.0

    # --- Deadband + cooldown --------------------------------------------- #
    deadband: float = 0.02
    cooldown_seconds: int = 300


class MonitoringAgent:
    """Deterministic Level-1 monitoring agent (BRD §24).

    Evaluates whether portfolio conditions or hedge characteristics have
    changed enough to warrant a Level-2 intelligent reassessment.

    Guarantees:
    - Purely deterministic checks based on quantitative thresholds.
    - Zero execution path: no broker, no order creation or submission methods.
    """

    def __init__(
        self,
        thresholds: MonitoringThresholds | None = None,
        repo: MonitoringRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.thresholds = thresholds or MonitoringThresholds(
            drawdown_pct=cfg.drawdown_trigger_pct,
            hedge_drift_pct=cfg.hedge_drift_threshold_pct,
        )
        self.repo = repo

    # ----------------------------------------------------------------------- #
    # Level-1 Deterministic Checks
    # ----------------------------------------------------------------------- #

    def check_drawdown(
        self, context: HedgeContext, threshold: float | None = None
    ) -> TriggerObservation | None:
        """Check if portfolio drawdown breaches the trigger threshold."""
        dd = context.portfolio_state.drawdown
        if dd is None:
            return None

        val = abs(dd)
        limit = threshold if threshold is not None else self.thresholds.drawdown_pct
        if val >= limit:
            return TriggerObservation(
                trigger_type=TriggerType.DRAWDOWN_LIMIT,
                observed_at=context.timestamp,
                observed_value=round(val, 4),
                threshold=round(limit, 4),
                detail=f"Portfolio drawdown of {val:.2%} reached or breached threshold of {limit:.2%}",
                breached=True,
            )
        return None

    def check_hedge_drift(
        self, context: HedgeContext, threshold: float | None = None
    ) -> TriggerObservation | None:
        """Check if difference between current and target hedge ratio exceeds drift threshold."""
        current = (
            context.current_hedge.hedge_ratio
            if context.current_hedge.hedge_ratio is not None
            else 0.0
        )
        target = (
            context.current_hedge.target_hedge_ratio
            if context.current_hedge.target_hedge_ratio is not None
            else (context.objective.target_hedge_ratio or 0.0)
        )
        drift = abs(current - target)
        limit = threshold if threshold is not None else self.thresholds.hedge_drift_pct

        if drift > limit:
            return TriggerObservation(
                trigger_type=TriggerType.PORTFOLIO_DELTA,
                observed_at=context.timestamp,
                observed_value=round(drift, 4),
                threshold=round(limit, 4),
                detail=(
                    f"Hedge drift of {drift:.2%} (|current {current:.2f} - "
                    f"target {target:.2f}|) exceeded threshold of {limit:.2%}"
                ),
                breached=True,
            )
        return None

    def check_volatility(
        self,
        context: HedgeContext,
        vol_threshold: float | None = None,
        vix_threshold: float | None = None,
    ) -> TriggerObservation | None:
        """Check if realized volatility or VIX breaches threshold limits."""
        vol = context.portfolio_state.volatility
        vix = context.market_state.vix if context.market_state else None
        v_limit = vol_threshold if vol_threshold is not None else self.thresholds.volatility
        vix_limit = vix_threshold if vix_threshold is not None else self.thresholds.vix

        vol_breached = vol is not None and vol >= v_limit
        vix_breached = vix is not None and vix >= vix_limit

        if vol_breached or vix_breached:
            observed_val = vol if vol is not None else vix
            return TriggerObservation(
                trigger_type=TriggerType.VOLATILITY_SPIKE,
                observed_at=context.timestamp,
                observed_value=round(observed_val, 4) if observed_val is not None else None,
                threshold=round(v_limit, 4),
                detail=f"Volatility spike detected (vol={vol}, vix={vix}) vs limit {v_limit}",
                breached=True,
            )
        return None

    def check_exposure(
        self, context: HedgeContext, threshold: float | None = None
    ) -> TriggerObservation | None:
        """Check if portfolio gross exposure exceeds maximum limits."""
        gross = context.portfolio_state.gross_exposure
        if gross is None:
            return None

        limit = threshold if threshold is not None else self.thresholds.gross_exposure
        if gross > limit:
            return TriggerObservation(
                trigger_type=TriggerType.PORTFOLIO_DELTA,
                observed_at=context.timestamp,
                observed_value=round(gross, 4),
                threshold=round(limit, 4),
                detail=f"Gross exposure of {gross:.2f} exceeded threshold of {limit:.2f}",
                breached=True,
            )
        return None

    def check_expiration(
        self, context: HedgeContext, threshold_days: float | None = None
    ) -> TriggerObservation | None:
        """Check if active hedge options are approaching expiration."""
        exp: date | None = context.current_hedge.expiration
        if exp is None and context.current_hedge.legs:
            # Check candidate expirations in active legs
            leg_exps = [
                leg.expiration
                for leg in context.current_hedge.legs
                if getattr(leg, "expiration", None)
            ]
            if leg_exps:
                exp = min(
                    datetime.fromisoformat(str(e)).date() if isinstance(e, str) else e
                    for e in leg_exps
                )

        if not context.current_hedge.active or exp is None:
            return None

        ctx_date = context.timestamp.date() if isinstance(context.timestamp, datetime) else date.today()
        days_to_exp = float((exp - ctx_date).days)
        limit = threshold_days if threshold_days is not None else self.thresholds.days_to_expiration

        if days_to_exp <= limit:
            return TriggerObservation(
                trigger_type=TriggerType.TIME_ELAPSED,
                observed_at=context.timestamp,
                observed_value=round(days_to_exp, 2),
                threshold=round(limit, 2),
                detail=f"Days to hedge expiration ({days_to_exp:.1f}d) reached or breached threshold of {limit:.1f}d",
                breached=True,
            )
        return None

    def check_major_state_change(
        self, context: HedgeContext
    ) -> TriggerObservation | None:
        """Check for major regime shifts, correlation breakdown, or severe news shock."""
        reasons: list[str] = []

        # 1. Beta breakdown / extreme divergence
        beta = context.portfolio_state.beta
        if beta is not None and (beta < self.thresholds.beta_min or beta > self.thresholds.beta_max):
            reasons.append(f"Beta anomaly ({beta:.2f} outside [{self.thresholds.beta_min}, {self.thresholds.beta_max}])")

        # 2. Severe negative news or major news event
        for item in context.news_context:
            if item.is_event:
                reasons.append(f"Major market event: {item.headline}")
                break
            if item.sentiment is not None and item.sentiment <= self.thresholds.news_sentiment_min:
                reasons.append(f"Severe negative sentiment ({item.sentiment:.2f}): {item.headline}")
                break

        # 3. Regime shock (HIGH_VOL or RISK_OFF)
        if context.market_state and context.market_state.regime in ("HIGH_VOL", "RISK_OFF"):
            if any(n.is_event for n in context.news_context):
                reasons.append(f"Regime shock ({context.market_state.regime}) with event")

        if reasons:
            return TriggerObservation(
                trigger_type=TriggerType.CORRELATION_BREAKDOWN,
                observed_at=context.timestamp,
                observed_value=beta,
                threshold=self.thresholds.beta_max,
                detail="; ".join(reasons),
                breached=True,
            )
        return None

    # ----------------------------------------------------------------------- #
    # Aggregation & Evaluation
    # ----------------------------------------------------------------------- #

    def evaluate_all_triggers(self, context: HedgeContext) -> list[TriggerObservation]:
        """Execute all six Level-1 checks and return any breached observations."""
        checks = [
            self.check_drawdown(context),
            self.check_hedge_drift(context),
            self.check_volatility(context),
            self.check_exposure(context),
            self.check_expiration(context),
            self.check_major_state_change(context),
        ]
        return [obs for obs in checks if obs is not None]

    def evaluate(
        self,
        context: HedgeContext,
        previous_state: MonitoringState | None = None,
    ) -> MonitoringState:
        """Evaluate Level-1 checks against context and snapshot the MonitoringState.

        Persists any fired trigger events and the resulting monitoring state
        if a repository was injected.
        """
        observations = self.evaluate_all_triggers(context)
        active_triggers = [obs.trigger_type for obs in observations if obs.breached]

        # Calculate time to expiration
        days_to_exp: float | None = None
        if context.current_hedge.expiration:
            ctx_date = context.timestamp.date() if isinstance(context.timestamp, datetime) else date.today()
            days_to_exp = float((context.current_hedge.expiration - ctx_date).days)

        # Cooldown state preservation
        cooldown_until = previous_state.cooldown_until if previous_state else None
        now_utc = datetime.now(timezone.utc)
        in_cooldown = cooldown_until is not None and cooldown_until > now_utc

        target_hedge = (
            context.current_hedge.target_hedge_ratio
            if context.current_hedge.target_hedge_ratio is not None
            else context.objective.target_hedge_ratio
        )

        state = MonitoringState(
            cycle_id=context.cycle_id,
            as_of=now_utc,
            portfolio_value=context.portfolio_state.total_value,
            drawdown=context.portfolio_state.drawdown,
            volatility=context.portfolio_state.volatility,
            gross_exposure=context.portfolio_state.gross_exposure,
            hedge_ratio=context.current_hedge.hedge_ratio,
            target_hedge_ratio=target_hedge,
            hedge_pnl=context.current_hedge.hedge_pnl,
            time_to_expiration_days=days_to_exp,
            trigger_history=observations,
            active_triggers=active_triggers,
            cooldown_until=cooldown_until,
            in_cooldown=in_cooldown,
            reassessment_recommended=bool(active_triggers),
        )

        if self.repo is not None:
            self._persist_evaluation(state, observations)

        return state

    def _persist_evaluation(
        self, state: MonitoringState, observations: list[TriggerObservation]
    ) -> None:
        """Persist fired triggers and monitoring state snapshot."""
        if self.repo is None:
            return
        try:
            from backend.db.monitoring_repo import (
                MonitoringEventRecord,
                MonitoringStateRecord,
            )

            # 1. Record fired trigger events
            for obs in observations:
                threshold_dec = (
                    decimal.Decimal(str(obs.threshold))
                    if obs.threshold is not None
                    else None
                )
                self.repo.record_event(
                    MonitoringEventRecord(
                        cycle_id=state.cycle_id,
                        trigger_type=obs.trigger_type,
                        observed={
                            "observed_value": obs.observed_value,
                            "detail": obs.detail,
                        },
                        threshold=threshold_dec,
                        fired_at=obs.observed_at,
                    )
                )

            # 2. Save current monitoring state snapshot
            curr_hedge = (
                decimal.Decimal(str(state.hedge_ratio))
                if state.hedge_ratio is not None
                else decimal.Decimal("0")
            )
            tgt_hedge = (
                decimal.Decimal(str(state.target_hedge_ratio))
                if state.target_hedge_ratio is not None
                else decimal.Decimal("0")
            )

            self.repo.save_state(
                MonitoringStateRecord(
                    cycle_id=state.cycle_id,
                    current_hedge=curr_hedge,
                    target_hedge=tgt_hedge,
                    cooldown_until=state.cooldown_until,
                    trigger_history=[t.model_dump(mode="json") for t in state.trigger_history],
                    monitoring_status="ACTIVE",
                    detail={
                        "reassessment_recommended": state.reassessment_recommended,
                        "active_triggers": [t.value for t in state.active_triggers],
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "MonitoringAgent: persistence failed for cycle %s", state.cycle_id
            )


def evaluate_level1_checks(
    context: HedgeContext,
    thresholds: MonitoringThresholds | None = None,
    repo: MonitoringRepository | None = None,
) -> MonitoringState:
    """Convenience helper to evaluate Level-1 monitoring checks."""
    return MonitoringAgent(thresholds=thresholds, repo=repo).evaluate(context)
