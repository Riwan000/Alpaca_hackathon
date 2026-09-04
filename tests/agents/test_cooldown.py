"""Tests for the post-adjustment cooldown gate — Task P7-BE-4 / Issue #172.

After a hedge adjustment a cooldown window is stamped; normal triggers inside it
are suppressed, an ``is_emergency`` trigger bypasses it. Outside the window (no
cooldown, or it has elapsed) everything passes.
"""

from __future__ import annotations

import datetime as _dt

from backend.agents.monitoring.agent import MonitoringThresholds
from backend.agents.monitoring.triggers import (
    TriggerEngine,
    apply_cooldown,
    start_cooldown,
)
from backend.models.enums import StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.monitoring import TriggerObservation

_NOW = _dt.datetime(2026, 9, 4, 15, 0, tzinfo=_dt.timezone.utc)
_THR = MonitoringThresholds()


def _obs(trigger_type: TriggerType, *, is_emergency: bool = False) -> TriggerObservation:
    return TriggerObservation(
        trigger_type=trigger_type,
        observed_at=_NOW,
        observed_value=0.5,
        threshold=0.1,
        detail="synthetic",
        breached=True,
        is_emergency=is_emergency,
    )


_NORMAL = _obs(TriggerType.PORTFOLIO_DELTA)
_EMERGENCY = _obs(TriggerType.DRAWDOWN_LIMIT, is_emergency=True)


def _context(*, drawdown: float, hedge_ratio: float, vix: float = 18.0) -> HedgeContext:
    return HedgeContext(
        cycle_id="cyc-cd-001",
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
            drawdown=drawdown,
            volatility=0.18,
            gross_exposure=0.70,
            beta=1.0,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=vix, index_trend="SIDEWAYS"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=0.80,
            expiration=(_NOW + _dt.timedelta(days=40)).date(),
        ),
    )


# --------------------------------------------------------------------------- #
# apply_cooldown
# --------------------------------------------------------------------------- #


def test_normal_trigger_suppressed_inside_cooldown():
    until = _NOW + _dt.timedelta(minutes=5)
    assert apply_cooldown([_NORMAL], cooldown_until=until, now=_NOW) == []


def test_emergency_trigger_bypasses_cooldown():
    until = _NOW + _dt.timedelta(minutes=5)
    kept = apply_cooldown([_NORMAL, _EMERGENCY], cooldown_until=until, now=_NOW)
    assert kept == [_EMERGENCY]


def test_no_cooldown_passes_everything():
    assert apply_cooldown(
        [_NORMAL, _EMERGENCY], cooldown_until=None, now=_NOW
    ) == [_NORMAL, _EMERGENCY]


def test_elapsed_cooldown_passes_everything():
    past = _NOW - _dt.timedelta(seconds=1)
    assert apply_cooldown([_NORMAL], cooldown_until=past, now=_NOW) == [_NORMAL]


def test_cooldown_boundary_is_open():
    # now == cooldown_until -> the window is over.
    assert apply_cooldown([_NORMAL], cooldown_until=_NOW, now=_NOW) == [_NORMAL]


# --------------------------------------------------------------------------- #
# start_cooldown
# --------------------------------------------------------------------------- #


def test_start_cooldown_uses_threshold_default():
    assert start_cooldown(_NOW, thresholds=_THR) == _NOW + _dt.timedelta(
        seconds=_THR.cooldown_seconds
    )


def test_start_cooldown_explicit_seconds():
    assert start_cooldown(_NOW, seconds=60) == _NOW + _dt.timedelta(seconds=60)


# --------------------------------------------------------------------------- #
# Confirm (#172): adjust, then trip a normal trigger (suppressed) and an
# emergency trigger (passes) — through the full engine.
# --------------------------------------------------------------------------- #


def test_engine_suppresses_normal_but_passes_emergency_during_cooldown():
    engine = TriggerEngine(_THR)
    cooldown_until = start_cooldown(_NOW, thresholds=_THR)

    # A normal hedge-drift trigger immediately after the adjustment: suppressed.
    normal_ctx = _context(drawdown=-0.02, hedge_ratio=0.40)  # drift 0.40
    assert engine.evaluate(normal_ctx, cooldown_until=cooldown_until, now=_NOW) == []

    # A deep-drawdown emergency in the same window: passes.
    emergency_ctx = _context(drawdown=-0.25, hedge_ratio=0.80)
    fired = engine.evaluate(emergency_ctx, cooldown_until=cooldown_until, now=_NOW)
    assert len(fired) == 1
    assert fired[0].is_emergency is True
    assert fired[0].trigger_type == TriggerType.DRAWDOWN_LIMIT

    # Once the window elapses, the normal trigger fires again.
    after = cooldown_until + _dt.timedelta(seconds=1)
    reopened = engine.evaluate(normal_ctx, cooldown_until=cooldown_until, now=after)
    assert [o.trigger_type for o in reopened] == [TriggerType.PORTFOLIO_DELTA]
