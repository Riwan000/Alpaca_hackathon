"""Tests for the Monitoring trigger evaluators — Task P7-BE-2 / Issue #170.

One focused case per trigger type: synthesize the condition and assert the
matching :class:`TriggerType` is emitted with a well-formed payload
(``observed_value`` / ``threshold`` / ``observed_at`` / ``detail``). The
aggregate helper is covered at the end.
"""

from __future__ import annotations

import datetime as _dt

from backend.agents.monitoring.agent import MonitoringThresholds
from backend.agents.monitoring.triggers import (
    evaluate_drawdown_change,
    evaluate_emergency,
    evaluate_event,
    evaluate_expiration,
    evaluate_hedge_drift,
    evaluate_triggers,
    evaluate_volatility_change,
)
from backend.models.enums import StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    NewsItem,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState

_NOW = _dt.datetime(2026, 9, 4, 15, 0, tzinfo=_dt.timezone.utc)
_THR = MonitoringThresholds()


def _make_context(
    *,
    drawdown: float | None = -0.02,
    volatility: float | None = 0.18,
    beta: float | None = 1.05,
    hedge_ratio: float | None = 0.80,
    target_hedge_ratio: float | None = 0.80,
    vix: float | None = 18.0,
    hedge_active: bool = True,
    expiration_days: int = 30,
    news: list[NewsItem] | None = None,
) -> HedgeContext:
    exp_date = (_NOW + _dt.timedelta(days=expiration_days)).date()
    return HedgeContext(
        cycle_id="cyc-trg-001",
        timestamp=_NOW,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05,
            drawdown_tolerance_pct=0.10,
            target_hedge_ratio=target_hedge_ratio,
        ),
        portfolio_state=PortfolioState(
            total_value=100_000.0,
            cash=20_000.0,
            equity=80_000.0,
            buying_power=50_000.0,
            drawdown=drawdown,
            volatility=volatility,
            gross_exposure=0.80,
            beta=beta,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=vix, index_trend="SIDEWAYS"),
        current_hedge=CurrentHedge(
            active=hedge_active,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target_hedge_ratio,
            expiration=exp_date,
            hedge_pnl=0.0,
        ),
        news_context=news or [],
    )


def _prev_state(**kw: float) -> MonitoringState:
    return MonitoringState(cycle_id="cyc-prev", as_of=_NOW - _dt.timedelta(hours=1), **kw)


# --------------------------------------------------------------------------- #
# One focused case per trigger type
# --------------------------------------------------------------------------- #


def test_hedge_drift_trigger():
    ctx = _make_context(hedge_ratio=0.60, target_hedge_ratio=0.80)
    obs = evaluate_hedge_drift(ctx, _THR)

    assert obs is not None
    assert obs.trigger_type == TriggerType.PORTFOLIO_DELTA
    assert obs.observed_value == 0.20
    assert obs.threshold == 0.05
    assert obs.observed_at == _NOW
    assert obs.breached is True
    assert obs.is_emergency is False

    # Inside target -> nothing.
    assert evaluate_hedge_drift(_make_context(hedge_ratio=0.80), _THR) is None


def test_drawdown_change_trigger():
    ctx = _make_context(drawdown=-0.09)
    obs = evaluate_drawdown_change(ctx, _prev_state(drawdown=-0.02), _THR)

    assert obs is not None
    assert obs.trigger_type == TriggerType.DRAWDOWN_LIMIT
    assert obs.observed_value == 0.07  # |(-0.09) - (-0.02)|
    assert obs.threshold == 0.03
    assert obs.is_emergency is False

    # A small move, and the no-baseline case, both stay quiet.
    assert evaluate_drawdown_change(ctx, _prev_state(drawdown=-0.07), _THR) is None
    assert evaluate_drawdown_change(ctx, None, _THR) is None


def test_volatility_change_trigger():
    ctx = _make_context(volatility=0.40)
    obs = evaluate_volatility_change(ctx, _prev_state(volatility=0.18), _THR)

    assert obs is not None
    assert obs.trigger_type == TriggerType.VOLATILITY_SPIKE
    assert obs.observed_value == 0.22
    assert obs.threshold == 0.10

    assert evaluate_volatility_change(ctx, _prev_state(volatility=0.34), _THR) is None
    assert evaluate_volatility_change(ctx, None, _THR) is None


def test_event_trigger():
    flagged = NewsItem(
        headline="Emergency Fed rate decision",
        ts=_NOW,
        symbols=["SPY"],
        is_event=True,
    )
    obs = evaluate_event(_make_context(news=[flagged]), _THR)
    assert obs is not None
    assert obs.trigger_type == TriggerType.CORRELATION_BREAKDOWN
    assert "Major market event" in obs.detail

    # Severe negative sentiment is also an event trigger.
    grim = NewsItem(
        headline="DOJ antitrust suit filed",
        ts=_NOW,
        symbols=["AAPL"],
        sentiment=-0.85,
    )
    obs2 = evaluate_event(_make_context(news=[grim]), _THR)
    assert obs2 is not None
    assert obs2.trigger_type == TriggerType.CORRELATION_BREAKDOWN
    assert obs2.observed_value == -0.85
    assert "Severe negative sentiment" in obs2.detail

    # Benign news -> nothing.
    calm = NewsItem(headline="Company hits earnings", ts=_NOW, sentiment=0.6)
    assert evaluate_event(_make_context(news=[calm]), _THR) is None


def test_expiration_trigger():
    obs = evaluate_expiration(_make_context(hedge_active=True, expiration_days=3), _THR)
    assert obs is not None
    assert obs.trigger_type == TriggerType.TIME_ELAPSED
    assert obs.observed_value == 3.0
    assert obs.threshold == 7.0

    # Far from expiry, or hedge inactive -> nothing.
    assert evaluate_expiration(_make_context(expiration_days=30), _THR) is None
    assert (
        evaluate_expiration(_make_context(hedge_active=False, expiration_days=2), _THR)
        is None
    )


def test_emergency_trigger():
    # Deep drawdown -> emergency, bypasses cooldown downstream.
    obs = evaluate_emergency(_make_context(drawdown=-0.20), _THR)
    assert obs is not None
    assert obs.trigger_type == TriggerType.DRAWDOWN_LIMIT
    assert obs.is_emergency is True
    assert obs.observed_value == 0.20
    assert "EMERGENCY" in obs.detail

    # Volatility blow-out via VIX -> emergency on the volatility axis.
    obs2 = evaluate_emergency(_make_context(drawdown=-0.03, vix=55.0), _THR)
    assert obs2 is not None
    assert obs2.trigger_type == TriggerType.VOLATILITY_SPIKE
    assert obs2.is_emergency is True

    # Ordinary conditions -> no emergency.
    assert evaluate_emergency(_make_context(drawdown=-0.04, vix=20.0), _THR) is None


# --------------------------------------------------------------------------- #
# Aggregate helper
# --------------------------------------------------------------------------- #


def test_evaluate_triggers_collects_each_fired_type():
    ctx = _make_context(
        drawdown=-0.09,
        volatility=0.40,
        hedge_ratio=0.50,
        target_hedge_ratio=0.80,
        expiration_days=2,
    )
    prev = _prev_state(drawdown=-0.02, volatility=0.18)

    fired = {obs.trigger_type for obs in evaluate_triggers(ctx, prev, _THR)}
    assert TriggerType.PORTFOLIO_DELTA in fired
    assert TriggerType.DRAWDOWN_LIMIT in fired
    assert TriggerType.VOLATILITY_SPIKE in fired
    assert TriggerType.TIME_ELAPSED in fired


def test_evaluate_triggers_quiet_context_emits_nothing():
    ctx = _make_context(
        drawdown=-0.02,
        volatility=0.18,
        hedge_ratio=0.80,
        target_hedge_ratio=0.80,
        expiration_days=45,
        vix=16.0,
    )
    assert evaluate_triggers(ctx, _prev_state(drawdown=-0.02, volatility=0.18), _THR) == []


def test_emergency_is_listed_first():
    ctx = _make_context(drawdown=-0.20, hedge_ratio=0.40, target_hedge_ratio=0.80)
    fired = evaluate_triggers(ctx, None, _THR)
    assert fired[0].is_emergency is True
