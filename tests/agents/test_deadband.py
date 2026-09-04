"""Tests for the deadband filter — Task P7-BE-3 / Issue #171.

A deviation that clears its firing threshold by no more than the deadband is
sensor noise and must be suppressed; clearing it by more than the deadband
fires. Emergencies, countdown triggers and categorical events pass through.
"""

from __future__ import annotations

import datetime as _dt

from backend.agents.monitoring.agent import MonitoringThresholds
from backend.agents.monitoring.triggers import (
    TriggerEngine,
    apply_deadband,
    evaluate_triggers,
)
from backend.models.enums import StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    PortfolioState,
)
from backend.models.monitoring import TriggerObservation

_NOW = _dt.datetime(2026, 9, 4, 15, 0, tzinfo=_dt.timezone.utc)
_THR = MonitoringThresholds()  # hedge_drift_pct=0.05, deadband=0.02


def _obs(
    trigger_type: TriggerType,
    observed_value: float | None,
    threshold: float | None,
    *,
    is_emergency: bool = False,
) -> TriggerObservation:
    return TriggerObservation(
        trigger_type=trigger_type,
        observed_at=_NOW,
        observed_value=observed_value,
        threshold=threshold,
        detail="synthetic",
        breached=True,
        is_emergency=is_emergency,
    )


def _drift_context(hedge_ratio: float) -> HedgeContext:
    return HedgeContext(
        cycle_id="cyc-db-001",
        timestamp=_NOW,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05,
            drawdown_tolerance_pct=0.10,
            target_hedge_ratio=0.80,
        ),
        portfolio_state=PortfolioState(
            total_value=100_000.0,
            cash=20_000.0,
            equity=80_000.0,
            buying_power=50_000.0,
            drawdown=-0.01,
            volatility=0.15,
            gross_exposure=0.70,
            beta=1.0,
        ),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=0.80,
            expiration=(_NOW + _dt.timedelta(days=40)).date(),
        ),
    )


# --------------------------------------------------------------------------- #
# Unit: apply_deadband on hand-built observations
# --------------------------------------------------------------------------- #


def test_excess_inside_band_is_dropped():
    # observed 0.06 vs threshold 0.05 -> excess 0.01 <= deadband 0.02
    inside = _obs(TriggerType.PORTFOLIO_DELTA, 0.06, 0.05)
    assert apply_deadband([inside], 0.02) == []


def test_excess_outside_band_is_kept():
    # observed 0.10 vs threshold 0.05 -> excess 0.05 > deadband 0.02
    outside = _obs(TriggerType.PORTFOLIO_DELTA, 0.10, 0.05)
    assert apply_deadband([outside], 0.02) == [outside]


def test_band_boundary_excludes_equal_excess():
    # Excess exactly equal to the band is still noise — strictly-greater wins.
    obs = _obs(TriggerType.DRAWDOWN_LIMIT, 0.09, 0.03)
    excess = abs(0.09) - abs(0.03)  # identical arithmetic to the filter
    assert apply_deadband([obs], excess) == []
    assert apply_deadband([obs], excess - 1e-6) == [obs]


def test_emergency_bypasses_deadband():
    tiny_excess_emergency = _obs(
        TriggerType.DRAWDOWN_LIMIT, 0.151, 0.15, is_emergency=True
    )
    assert apply_deadband([tiny_excess_emergency], 0.02) == [tiny_excess_emergency]


def test_countdown_and_event_pass_through_untouched():
    expiry = _obs(TriggerType.TIME_ELAPSED, 3.0, 7.0)
    event = _obs(TriggerType.CORRELATION_BREAKDOWN, None, -0.60)
    kept = apply_deadband([expiry, event], 0.02)
    assert kept == [expiry, event]


def test_custom_band_widens_suppression():
    obs = _obs(TriggerType.VOLATILITY_SPIKE, 0.12, 0.10)  # excess 0.02
    assert apply_deadband([obs], 0.01) == [obs]  # 0.02 > 0.01 -> kept
    assert apply_deadband([obs], 0.05) == []  # 0.02 <= 0.05 -> dropped


def test_default_band_used_when_none():
    obs = _obs(TriggerType.PORTFOLIO_DELTA, 0.06, 0.05)  # excess 0.01, default band 0.02
    assert apply_deadband([obs]) == []


# --------------------------------------------------------------------------- #
# End-to-end: evaluate -> deadband
# --------------------------------------------------------------------------- #


def test_drift_just_inside_band_produces_no_event():
    # drift 0.06 clears the 0.05 threshold by 0.01 -> inside the 0.02 band.
    raw = evaluate_triggers(_drift_context(hedge_ratio=0.74), None, _THR)
    assert [o.trigger_type for o in raw] == [TriggerType.PORTFOLIO_DELTA]
    assert apply_deadband(raw, _THR.deadband) == []


def test_drift_just_outside_band_produces_one_event():
    # drift 0.09 clears the 0.05 threshold by 0.04 -> outside the 0.02 band.
    raw = evaluate_triggers(_drift_context(hedge_ratio=0.71), None, _THR)
    kept = apply_deadband(raw, _THR.deadband)
    assert len(kept) == 1
    assert kept[0].trigger_type == TriggerType.PORTFOLIO_DELTA


def test_nudge_below_deadband_fires_nothing_through_engine():
    # Confirm (#171): nudge the hedge ratio by 0.01 (< deadband); nothing fires.
    engine = TriggerEngine(_THR)
    assert engine.evaluate(_drift_context(hedge_ratio=0.79)) == []
