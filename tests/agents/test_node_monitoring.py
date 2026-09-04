"""``MONITORING`` node runs Level 1 each cycle, escalates once on a trigger — P7-BE-8 / issue #176.

Confirms:
- a quiet cycle (no trigger) ends clean and terminal — no reassessment;
- a triggered cycle dispatches Level 2 exactly once (no loop) and records it;
- a state that is already a reassessment cycle (``reassessment_origin``) does not
  escalate again;
- run two cycles against one DB — the quiet one ends clean, the triggered one
  escalates and writes a ``reassessment_events`` row.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import pytest

from backend.agents.orchestrator.nodes import OrchestratorDeps, monitoring_node
from backend.db.monitoring_repo import MonitoringRepository
from backend.models.common import OptionLeg
from backend.models.enums import OptionRight, OrderSide, StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState

pytestmark = pytest.mark.integration


def _ctx(*, hedge_ratio: float, target: float, volatility: float = 0.12, drawdown: float = -0.01) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp = (now + _dt.timedelta(days=30)).date()
    return HedgeContext(
        cycle_id="cyc-mon-node",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05, drawdown_tolerance_pct=0.10, target_hedge_ratio=target
        ),
        portfolio_state=PortfolioState(
            total_value=250_000.0, cash=100_000.0, equity=150_000.0, buying_power=120_000.0,
            drawdown=drawdown, volatility=volatility, beta=1.0, gross_exposure=0.6,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=14.0, index_trend="UP"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target,
            expiration=exp,
            hedge_pnl=120.0,
            legs=[
                OptionLeg(
                    underlying="AAPL", right=OptionRight.PUT, side=OrderSide.BUY,
                    strike=150.0, expiration=exp, quantity=4,
                )
            ],
        ),
    )


def _calm_ctx() -> HedgeContext:
    # hedge sits on target, vol low, drawdown flat — nothing fires
    return _ctx(hedge_ratio=0.50, target=0.50, volatility=0.11, drawdown=-0.005)


def _stabilizing_drift_ctx() -> HedgeContext:
    # less hedge needed now (target dropped) -> hedge_drift PORTFOLIO_DELTA fires
    return _ctx(hedge_ratio=0.80, target=0.40, volatility=0.11, drawdown=-0.004)


def _deps(engine: Any, *, outcome: str = "DECREASE") -> OrchestratorDeps:
    from tests.conftest import FakeLLMClient

    fake = FakeLLMClient()
    fake.response_content = json.dumps(
        {
            "outcome": outcome,
            "rationale": f"stub {outcome}",
            "confidence": 0.8,
            "verdict": "APPROVE",
        }
    )
    return OrchestratorDeps(engine=engine, llm_client=fake)


def test_quiet_cycle_ends_clean(migrated_engine) -> None:
    node = monitoring_node(_deps(migrated_engine))

    out = node({"cycle_id": "cyc-mon-node", "hedge_context": _calm_ctx()})

    assert isinstance(out["monitoring_state"], MonitoringState)
    assert out["monitoring_state"].active_triggers == []
    assert "reassessment_decision" not in out
    assert out["current_node"] == "MONITORING"
    assert "route" not in out  # still terminal

    row = MonitoringRepository(migrated_engine).get_latest_state()
    assert row is not None and row.monitoring_status == "ACTIVE"
    assert MonitoringRepository(migrated_engine).list_reassessments("cyc-mon-node") == []


def test_triggered_cycle_dispatches_level2_once(migrated_engine, monkeypatch) -> None:
    from backend.agents.monitoring import reassessment as _reassess

    calls = {"n": 0}
    real_assess = _reassess.ReassessmentAgent.assess

    def _counting_assess(self, ctx, state, **kw):  # noqa: ANN001
        calls["n"] += 1
        return real_assess(self, ctx, state, **kw)

    monkeypatch.setattr(_reassess.ReassessmentAgent, "assess", _counting_assess)

    node = monitoring_node(_deps(migrated_engine))
    out = node({"cycle_id": "cyc-mon-node", "hedge_context": _stabilizing_drift_ctx()})

    assert TriggerType.PORTFOLIO_DELTA in out["monitoring_state"].active_triggers
    assert calls["n"] == 1  # dispatched once, not looping
    assert out["reassessment_decision"].outcome.value == "DECREASE"
    assert out["reassessment_result"]["outcome"] == "DECREASE"
    assert any("Level 2 dispatched" in n for n in out["notes"])
    assert out["current_node"] == "MONITORING"
    assert "route" not in out

    repo = MonitoringRepository(migrated_engine)
    reassessments = repo.list_reassessments("cyc-mon-node")
    assert len(reassessments) == 1
    assert str(reassessments[0].outcome) == "DECREASE"
    # the position change was taken through the gate and recorded
    assert repo.list_hedge_changes("cyc-mon-node")
    assert repo.get_latest_state().detail["reassessment"]["outcome"] == "DECREASE"


def test_reassessment_origin_does_not_escalate_again(migrated_engine) -> None:
    node = monitoring_node(_deps(migrated_engine))

    out = node(
        {
            "cycle_id": "cyc-mon-node",
            "hedge_context": _stabilizing_drift_ctx(),
            "reassessment_origin": True,
        }
    )

    assert TriggerType.PORTFOLIO_DELTA in out["monitoring_state"].active_triggers
    assert "reassessment_decision" not in out
    assert MonitoringRepository(migrated_engine).list_reassessments("cyc-mon-node") == []


def test_two_cycles_quiet_then_triggered(migrated_engine) -> None:
    node = monitoring_node(_deps(migrated_engine))

    quiet = node({"cycle_id": "cyc-q", "hedge_context": _calm_ctx()})
    assert "reassessment_decision" not in quiet

    fired = node({"cycle_id": "cyc-t", "hedge_context": _stabilizing_drift_ctx()})
    assert "reassessment_decision" in fired

    repo = MonitoringRepository(migrated_engine)
    assert repo.list_reassessments("cyc-q") == []
    assert len(repo.list_reassessments("cyc-t")) == 1
