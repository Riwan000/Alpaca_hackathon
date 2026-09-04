"""Tests for Monitoring Agent Level-1 deterministic checks (Task P7-BE-1 / Issue #169).

Validates:
1. Purely deterministic checks fire ONLY past their quantitative thresholds and return None below.
2. The six check categories:
   - Drawdown (DRAWDOWN_LIMIT)
   - Hedge drift (PORTFOLIO_DELTA)
   - Volatility spike (VOLATILITY_SPIKE)
   - Exposure breach (PORTFOLIO_DELTA)
   - Expiration (TIME_ELAPSED)
   - Major state change / correlation breakdown (CORRELATION_BREAKDOWN)
3. Aggregated evaluate() produces correct MonitoringState, active_triggers, reassessment_recommended.
4. Cooldown preservation logic.
5. Snapshot persistence to database via MonitoringRepository.
6. Zero-execution invariant: MonitoringAgent has no execution path, no broker, and places zero orders.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy.engine import Engine

from backend.agents.monitoring.agent import (
    MonitoringAgent,
    MonitoringThresholds,
    evaluate_level1_checks,
)
from backend.db.monitoring_repo import MonitoringRepository
from backend.models.common import OptionLeg
from backend.models.enums import OptionRight, OrderSide, StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    NewsItem,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState


def _make_context(
    *,
    cycle_id: str = "cyc-mon-001",
    drawdown: float | None = -0.02,
    volatility: float | None = 0.18,
    gross_exposure: float | None = 0.80,
    beta: float | None = 1.05,
    hedge_ratio: float | None = 0.80,
    target_hedge_ratio: float | None = 0.80,
    vix: float | None = 18.0,
    regime: str = "LOW_VOL",
    hedge_active: bool = True,
    expiration_days: int = 30,
    news: list[NewsItem] | None = None,
) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp_date = (now + _dt.timedelta(days=expiration_days)).date()

    return HedgeContext(
        cycle_id=cycle_id,
        timestamp=now,
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
            positions=[],
            drawdown=drawdown,
            volatility=volatility,
            gross_exposure=gross_exposure,
            beta=beta,
        ),
        market_state=MarketState(
            regime=regime,
            vix=vix,
            index_trend="SIDEWAYS",
        ),
        current_hedge=CurrentHedge(
            active=hedge_active,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target_hedge_ratio,
            expiration=exp_date,
            hedge_pnl=250.0,
        ),
        news_context=news or [],
    )


# --------------------------------------------------------------------------- #
# Non-Trading Invariant Tests
# --------------------------------------------------------------------------- #


def test_monitoring_agent_has_no_execution_path():
    """Assert that MonitoringAgent has no execution or order placement capability."""
    agent = MonitoringAgent()

    # Verify absence of broker or execution attributes
    assert not hasattr(agent, "broker")
    assert not hasattr(agent, "alpaca")
    assert not hasattr(agent, "submit_order")
    assert not hasattr(agent, "create_order")
    assert not hasattr(agent, "place_order")
    assert not hasattr(agent, "execute_order")
    assert not hasattr(agent, "execute")

    # Feeding a drifted portfolio produces trigger observations with zero execution
    ctx = _make_context(hedge_ratio=0.20, target_hedge_ratio=0.80)
    state = agent.evaluate(ctx)

    assert TriggerType.PORTFOLIO_DELTA in state.active_triggers
    assert state.reassessment_recommended is True
    # State reflects triggers only; no order payload or execution receipt exists
    assert not hasattr(state, "orders")
    assert not hasattr(state, "executions")


# --------------------------------------------------------------------------- #
# Individual Level-1 Deterministic Checks
# --------------------------------------------------------------------------- #


class TestLevel1Checks:
    def test_check_drawdown(self):
        agent = MonitoringAgent(thresholds=MonitoringThresholds(drawdown_pct=0.05))

        # Safe: drawdown of 2% < 5% threshold
        ctx_safe = _make_context(drawdown=-0.02)
        assert agent.check_drawdown(ctx_safe) is None

        # Breached: drawdown of 6% >= 5% threshold
        ctx_breach = _make_context(drawdown=-0.06)
        obs = agent.check_drawdown(ctx_breach)
        assert obs is not None
        assert obs.trigger_type == TriggerType.DRAWDOWN_LIMIT
        assert obs.breached is True
        assert obs.observed_value == 0.06
        assert obs.threshold == 0.05

        # Edge case: drawdown is None
        ctx_none = _make_context(drawdown=None)
        assert agent.check_drawdown(ctx_none) is None

    def test_check_hedge_drift(self):
        agent = MonitoringAgent(thresholds=MonitoringThresholds(hedge_drift_pct=0.05))

        # Safe: drift |0.82 - 0.80| = 0.02 <= 0.05 threshold
        ctx_safe = _make_context(hedge_ratio=0.82, target_hedge_ratio=0.80)
        assert agent.check_hedge_drift(ctx_safe) is None

        # Breached: drift |0.60 - 0.80| = 0.20 > 0.05 threshold
        ctx_breach = _make_context(hedge_ratio=0.60, target_hedge_ratio=0.80)
        obs = agent.check_hedge_drift(ctx_breach)
        assert obs is not None
        assert obs.trigger_type == TriggerType.PORTFOLIO_DELTA
        assert obs.breached is True
        assert obs.observed_value == 0.20
        assert obs.threshold == 0.05

    def test_check_volatility(self):
        agent = MonitoringAgent(
            thresholds=MonitoringThresholds(volatility=0.30, vix=30.0)
        )

        # Safe: vol 0.20 < 0.30, vix 20 < 30
        ctx_safe = _make_context(volatility=0.20, vix=20.0)
        assert agent.check_volatility(ctx_safe) is None

        # Breached by realized vol
        ctx_vol_breach = _make_context(volatility=0.35, vix=22.0)
        obs1 = agent.check_volatility(ctx_vol_breach)
        assert obs1 is not None
        assert obs1.trigger_type == TriggerType.VOLATILITY_SPIKE
        assert obs1.breached is True

        # Breached by VIX
        ctx_vix_breach = _make_context(volatility=0.25, vix=34.5)
        obs2 = agent.check_volatility(ctx_vix_breach)
        assert obs2 is not None
        assert obs2.trigger_type == TriggerType.VOLATILITY_SPIKE
        assert obs2.breached is True

    def test_check_exposure(self):
        agent = MonitoringAgent(thresholds=MonitoringThresholds(gross_exposure=1.00))

        # Safe: gross exposure 0.90 <= 1.00
        ctx_safe = _make_context(gross_exposure=0.90)
        assert agent.check_exposure(ctx_safe) is None

        # Breached: gross exposure 1.25 > 1.00
        ctx_breach = _make_context(gross_exposure=1.25)
        obs = agent.check_exposure(ctx_breach)
        assert obs is not None
        assert obs.trigger_type == TriggerType.PORTFOLIO_DELTA
        assert obs.breached is True
        assert obs.observed_value == 1.25

        # None gross exposure
        ctx_none = _make_context(gross_exposure=None)
        assert agent.check_exposure(ctx_none) is None

    def test_check_expiration(self):
        agent = MonitoringAgent(thresholds=MonitoringThresholds(days_to_expiration=7.0))

        # Safe: 20 days to expiration > 7 days
        ctx_safe = _make_context(hedge_active=True, expiration_days=20)
        assert agent.check_expiration(ctx_safe) is None

        # Breached: 3 days to expiration <= 7 days
        ctx_breach = _make_context(hedge_active=True, expiration_days=3)
        obs = agent.check_expiration(ctx_breach)
        assert obs is not None
        assert obs.trigger_type == TriggerType.TIME_ELAPSED
        assert obs.breached is True
        assert obs.observed_value == 3.0

        # Inactive hedge does not fire expiration trigger
        ctx_inactive = _make_context(hedge_active=False, expiration_days=2)
        assert agent.check_expiration(ctx_inactive) is None

    def test_check_expiration_via_legs(self):
        agent = MonitoringAgent(thresholds=MonitoringThresholds(days_to_expiration=7.0))
        ctx = _make_context(hedge_active=True, expiration_days=30)
        near_exp = (_dt.date.today() + _dt.timedelta(days=4))
        ctx = ctx.model_copy(
            update={
                "current_hedge": CurrentHedge(
                    active=True,
                    strategy_type=StrategyType.PROTECTIVE_PUT,
                    hedge_ratio=0.80,
                    target_hedge_ratio=0.80,
                    expiration=None,
                    legs=[
                        OptionLeg(
                            underlying="AAPL",
                            right=OptionRight.PUT,
                            side=OrderSide.BUY,
                            strike=150.0,
                            expiration=near_exp,
                            quantity=2,
                        )
                    ],
                )
            }
        )
        obs = agent.check_expiration(ctx)
        assert obs is not None
        assert obs.trigger_type == TriggerType.TIME_ELAPSED
        assert obs.breached is True

    def test_check_major_state_change(self):
        agent = MonitoringAgent(
            thresholds=MonitoringThresholds(
                beta_min=0.0, beta_max=2.0, news_sentiment_min=-0.60
            )
        )

        # Safe: beta 1.10, positive news
        ctx_safe = _make_context(
            beta=1.10,
            news=[
                NewsItem(
                    headline="Strong earnings report",
                    ts=_dt.datetime.now(_dt.timezone.utc),
                    symbols=["AAPL"],
                    sentiment=0.75,
                )
            ],
        )
        assert agent.check_major_state_change(ctx_safe) is None

        # Breached: beta anomaly > 2.0
        ctx_beta_breach = _make_context(beta=2.45)
        obs1 = agent.check_major_state_change(ctx_beta_breach)
        assert obs1 is not None
        assert obs1.trigger_type == TriggerType.CORRELATION_BREAKDOWN
        assert "Beta anomaly" in obs1.detail

        # Breached: major news event shock
        ctx_event_breach = _make_context(
            news=[
                NewsItem(
                    headline="Emergency Fed Rate Hike Announced",
                    ts=_dt.datetime.now(_dt.timezone.utc),
                    symbols=["SPY"],
                    is_event=True,
                )
            ]
        )
        obs2 = agent.check_major_state_change(ctx_event_breach)
        assert obs2 is not None
        assert obs2.trigger_type == TriggerType.CORRELATION_BREAKDOWN
        assert "Major market event" in obs2.detail

        # Breached: severe negative news sentiment <= -0.60
        ctx_news_breach = _make_context(
            news=[
                NewsItem(
                    headline="DOJ files antitrust lawsuit against company",
                    ts=_dt.datetime.now(_dt.timezone.utc),
                    symbols=["AAPL"],
                    sentiment=-0.85,
                )
            ]
        )
        obs3 = agent.check_major_state_change(ctx_news_breach)
        assert obs3 is not None
        assert obs3.trigger_type == TriggerType.CORRELATION_BREAKDOWN
        assert "Severe negative sentiment" in obs3.detail


# --------------------------------------------------------------------------- #
# Aggregated Evaluation & Cooldown Tests
# --------------------------------------------------------------------------- #


def test_evaluate_clean_state():
    """Verify clean evaluation when no triggers are breached."""
    agent = MonitoringAgent()
    ctx = _make_context(
        drawdown=-0.01,
        hedge_ratio=0.80,
        target_hedge_ratio=0.80,
        volatility=0.15,
        vix=15.0,
        gross_exposure=0.70,
        beta=1.0,
        expiration_days=45,
    )
    state = agent.evaluate(ctx)

    assert isinstance(state, MonitoringState)
    assert state.cycle_id == "cyc-mon-001"
    assert state.active_triggers == []
    assert state.trigger_history == []
    assert state.reassessment_recommended is False
    assert state.in_cooldown is False


def test_evaluate_multiple_breaches_and_cooldown():
    """Verify evaluate() aggregates multiple breached triggers and checks cooldown."""
    agent = MonitoringAgent()
    ctx = _make_context(
        drawdown=-0.08,  # breached (> 5%)
        hedge_ratio=0.40,  # breached (|0.40 - 0.80| = 0.40 > 5%)
        target_hedge_ratio=0.80,
        volatility=0.38,  # breached (> 30%)
    )

    future_cooldown = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=30)
    prev_state = MonitoringState(
        cycle_id="cyc-prev",
        as_of=_dt.datetime.now(_dt.timezone.utc),
        portfolio_value=100_000.0,
        cooldown_until=future_cooldown,
    )

    state = agent.evaluate(ctx, previous_state=prev_state)

    assert state.reassessment_recommended is True
    assert TriggerType.DRAWDOWN_LIMIT in state.active_triggers
    assert TriggerType.PORTFOLIO_DELTA in state.active_triggers
    assert TriggerType.VOLATILITY_SPIKE in state.active_triggers
    assert len(state.trigger_history) >= 3
    assert state.in_cooldown is True
    assert state.cooldown_until == future_cooldown


def test_evaluate_level1_checks_helper():
    """Verify evaluate_level1_checks convenience helper function."""
    ctx = _make_context(drawdown=-0.09)
    state = evaluate_level1_checks(ctx)

    assert isinstance(state, MonitoringState)
    assert TriggerType.DRAWDOWN_LIMIT in state.active_triggers
    assert state.reassessment_recommended is True


# --------------------------------------------------------------------------- #
# Database Persistence Tests
# --------------------------------------------------------------------------- #


def test_monitoring_persistence(migrated_engine: Engine):
    """Verify that evaluate() persists fired events and state to the monitoring tables."""
    repo = MonitoringRepository(migrated_engine)
    agent = MonitoringAgent(repo=repo)

    ctx = _make_context(
        cycle_id="cyc-mon-db-test",
        drawdown=-0.08,
        hedge_ratio=0.50,
        target_hedge_ratio=0.80,
    )

    state = agent.evaluate(ctx)
    assert state.reassessment_recommended is True

    # 1. Check monitoring events persisted
    events = repo.list_events(cycle_id="cyc-mon-db-test")
    assert len(events) >= 2
    event_types = {e.trigger_type for e in events}
    assert TriggerType.DRAWDOWN_LIMIT.value in event_types
    assert TriggerType.PORTFOLIO_DELTA.value in event_types

    # 2. Check monitoring state persisted
    latest_state = repo.get_latest_state()
    assert latest_state is not None
    assert latest_state.cycle_id == "cyc-mon-db-test"
    assert float(latest_state.current_hedge) == pytest.approx(0.50)
    assert float(latest_state.target_hedge) == pytest.approx(0.80)
    assert latest_state.monitoring_status == "ACTIVE"
    assert latest_state.detail is not None
    assert latest_state.detail["reassessment_recommended"] is True
