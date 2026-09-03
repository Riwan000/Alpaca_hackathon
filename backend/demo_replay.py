"""Demo narrative replay script — task P8-BE-6 (BRD §37).

Reproduces the full 8-scene demo story deterministically:
1. Baseline Portfolio & Initial State
2. Volatility Shock & News Analysis
3. Four Strategy Hypotheses Generated
4. Strategy Selection & Risk Gate Approval
5. Order Execution (Multi-leg Option Fills & Slippage)
6. Level-1 Monitoring & Drift Tracking
7. Market Stabilization & Level-2 Reassessment (DECREASE)
8. Performance Time Series & Benchmark Cushioning
"""

from __future__ import annotations

import datetime as _dt
import decimal
from typing import Any

from sqlalchemy.engine import Engine

from backend.db.agent_runs_repo import AgentRunRecord, AgentRunRepository
from backend.db.monitoring_repo import (
    HedgeChangeRecord,
    MonitoringEventRecord,
    MonitoringRepository,
    MonitoringStateRecord,
    ReassessmentEventRecord,
)
from backend.db.orders_repo import FillRecord, OrderRecord, OrderRepository
from backend.db.performance_repo import PerformanceRecord, PerformanceRepository
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)
from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository
from backend.db.strategy_repo import (
    StrategyDecisionRecord,
    StrategyDecisionRepository,
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)
from backend.db.workflow_repo import WorkflowRepository
from backend.models.enums import (
    DecisionType,
    HedgeAction,
    OrderStatus,
    RiskVerdict,
    StrategyType,
    TriggerType,
    WorkflowNode,
    WorkflowStatus,
)


def replay_demo_narrative(engine: Engine, cycle_id: str = "demo_cycle_golden") -> dict[str, Any]:
    """Execute the full demo narrative script against ``engine``."""
    now = _dt.datetime.now(_dt.timezone.utc)
    t0 = now - _dt.timedelta(hours=4)
    t1 = now - _dt.timedelta(hours=3)
    t2 = now - _dt.timedelta(hours=2)
    t3 = now - _dt.timedelta(hours=1)
    t4 = now

    snap_repo = PortfolioSnapshotRepository(engine)
    agent_repo = AgentRunRepository(engine)
    hyp_repo = StrategyHypothesisRepository(engine)
    dec_repo = StrategyDecisionRepository(engine)
    risk_repo = RiskCheckRepository(engine)
    order_repo = OrderRepository(engine)
    mon_repo = MonitoringRepository(engine)
    perf_repo = PerformanceRepository(engine)
    wf_repo = WorkflowRepository(engine)

    # 1. Workflow state initialization
    wf_repo.set_state(cycle_id, WorkflowNode.INITIAL, WorkflowStatus.RUNNING)

    # 2. Portfolio Snapshot & Positions
    snap = snap_repo.save_with_positions(
        PortfolioSnapshotRecord(
            cycle_id=cycle_id,
            total_value=decimal.Decimal("1000000.0000"),
            cash=decimal.Decimal("200000.0000"),
            equity=decimal.Decimal("800000.0000"),
            buying_power=decimal.Decimal("400000.0000"),
            volatility=decimal.Decimal("0.2450"),
            beta=decimal.Decimal("1.1500"),
            drawdown=decimal.Decimal("-0.0700"),
            ts=t0,
        ),
        [
            PositionRecord(
                symbol="AAPL",
                qty=decimal.Decimal("2000.0000"),
                avg_price=decimal.Decimal("150.0000"),
                market_value=decimal.Decimal("360000.0000"),
                asset_class="EQUITY",
                side="BUY",
            ),
            PositionRecord(
                symbol="MSFT",
                qty=decimal.Decimal("1000.0000"),
                avg_price=decimal.Decimal("300.0000"),
                market_value=decimal.Decimal("440000.0000"),
                asset_class="EQUITY",
                side="BUY",
            ),
        ],
    )

    # 3. Agent Runs
    wf_repo.set_state(cycle_id, WorkflowNode.ANALYZING, WorkflowStatus.RUNNING)
    run_rec = agent_repo.create(
        AgentRunRecord(
            cycle_id=cycle_id,
            agent_name="MarketAnalysisAgent",
            inputs={"portfolio_value": 1000000},
            started_at=t0,
        )
    )
    agent_repo.finish(
        run_rec.id,
        outputs={"regime": "RISK_OFF", "vix": 28.5},
        duration_ms=2000,
    )

    # 4. Strategy Hypotheses
    wf_repo.set_state(cycle_id, WorkflowNode.STRATEGY_EVALUATION, WorkflowStatus.RUNNING)
    saved_hyps = hyp_repo.save_many(
        [
            StrategyHypothesisRecord(
                cycle_id=cycle_id,
                strategy_type="PROTECTIVE_PUT",
                verdict="ACCEPTED",
                legs=[{"underlying": "SPY", "right": "PUT", "strike": 500, "qty": 20}],
                metrics={"cost": 17000, "protection_pct": 0.90},
                rejection_reason=None,
            ),
            StrategyHypothesisRecord(
                cycle_id=cycle_id,
                strategy_type="COLLAR",
                verdict="ACCEPTED",
                legs=[
                    {"underlying": "SPY", "right": "PUT", "strike": 500, "qty": 20},
                    {"underlying": "SPY", "right": "CALL", "strike": 550, "qty": 20},
                ],
                metrics={"cost": 0, "protection_pct": 0.85},
                rejection_reason=None,
            ),
            StrategyHypothesisRecord(
                cycle_id=cycle_id,
                strategy_type="NO_HEDGE",
                verdict="REJECTED",
                legs=[],
                metrics={"cost": 0},
                rejection_reason="Drawdown (-7%) breaches risk tolerance threshold in high-vol regime.",
            ),
        ]
    )

    dec_repo.create(
        StrategyDecisionRecord(
            cycle_id=cycle_id,
            action="NEW_HEDGE",
            rationale="Protective Put provides max tail risk protection per dollar spent.",
            selected_hypothesis_id=saved_hyps[0].id,
            alternatives=[h.strategy_type for h in saved_hyps],
        )
    )

    # 5. Risk Check Gate
    wf_repo.set_state(cycle_id, WorkflowNode.RISK_CHECK, WorkflowStatus.RUNNING)
    risk_repo.create(
        RiskCheckRecord(
            cycle_id=cycle_id,
            verdict=RiskVerdict.APPROVE,
            checks=[
                {"name": "hedge_budget", "passed": True, "observed": 0.017, "limit": 0.05},
                {"name": "max_hedge_ratio", "passed": True, "observed": 0.20, "limit": 0.35},
                {"name": "buying_power", "passed": True},
            ],
            violations=[],
            warnings=["Elevated implied volatility into market close"],
            modifications=[],
        )
    )

    # 6. Order Submission & Fills
    wf_repo.set_state(cycle_id, WorkflowNode.EXECUTION, WorkflowStatus.RUNNING)
    order_repo.save_with_fills(
        OrderRecord(
            cycle_id=cycle_id,
            order_class="MLEG",
            status=OrderStatus.FILLED,
            legs=[{"underlying": "SPY", "right": "PUT", "strike": 500, "quantity": 20}],
            broker_order_id="alpaca_ord_demo_01",
            submitted_at=t1,
        ),
        [
            FillRecord(
                order_id=0,
                leg_symbol="SPY261218P00500000",
                qty=decimal.Decimal("20.0000"),
                price=decimal.Decimal("8.5500"),
                slippage=decimal.Decimal("0.0500"),
                filled_at=t1 + _dt.timedelta(seconds=2),
            )
        ],
    )

    # 7. Level-1 Monitoring & Level-2 Reassessment (Market Stabilizes)
    wf_repo.set_state(cycle_id, WorkflowNode.MONITORING, WorkflowStatus.RUNNING)
    trig_ev = mon_repo.record_event(
        MonitoringEventRecord(
            cycle_id=cycle_id,
            trigger_type=TriggerType.VOLATILITY_SPIKE,
            observed={"vix": 16.2, "iv_drop": -0.40},
            threshold=decimal.Decimal("18.0000"),
            fired_at=t2,
        )
    )

    reassess_ev = mon_repo.record_reassessment(
        ReassessmentEventRecord(
            cycle_id=cycle_id,
            trigger_event_id=trig_ev.id,
            outcome=HedgeAction.DECREASE,
            reason="Market stabilized with VIX normalizing to 16.2. Reducing put coverage by 50%.",
            context={"stabilized_vix": 16.2},
            created_at=t3,
        )
    )

    mon_repo.record_hedge_change(
        HedgeChangeRecord(
            cycle_id=cycle_id,
            reassessment_id=reassess_ev.id,
            before_hedge_ratio=decimal.Decimal("0.8000"),
            after_hedge_ratio=decimal.Decimal("0.3000"),
            delta=decimal.Decimal("-0.5000"),
            action=HedgeAction.DECREASE,
            reason="Unwound 10 contracts to recycle premium as volatility normalized.",
            created_at=t3,
        )
    )

    mon_repo.save_state(
        MonitoringStateRecord(
            cycle_id=cycle_id,
            current_hedge=decimal.Decimal("0.3000"),
            target_hedge=decimal.Decimal("0.3000"),
            monitoring_status="ACTIVE",
            trigger_history=[{"type": "VOLATILITY_FALL", "observed": 16.2}],
        )
    )

    # 8. Performance Records
    perf_repo.save(
        PerformanceRecord(
            cycle_id=cycle_id,
            portfolio_pnl=decimal.Decimal("-30000.0000"),
            hedge_pnl=decimal.Decimal("22000.0000"),
            net_pnl=decimal.Decimal("-8000.0000"),
            drawdown=decimal.Decimal("-0.0080"),
            hedge_cost=decimal.Decimal("1700.0000"),
            benchmark_pnl=decimal.Decimal("-30000.0000"),
            ts=t2,
        )
    )

    perf_repo.save(
        PerformanceRecord(
            cycle_id=cycle_id,
            portfolio_pnl=decimal.Decimal("-10000.0000"),
            hedge_pnl=decimal.Decimal("16000.0000"),
            net_pnl=decimal.Decimal("6000.0000"),
            drawdown=decimal.Decimal("0.0000"),
            hedge_cost=decimal.Decimal("1700.0000"),
            benchmark_pnl=decimal.Decimal("-10000.0000"),
            ts=t4,
        )
    )

    wf_repo.set_state(cycle_id, WorkflowNode.COMPLETED, WorkflowStatus.COMPLETED)

    return {
        "cycle_id": cycle_id,
        "snapshot_id": snap.snapshot.id,
        "status": "completed",
    }


if __name__ == "__main__":
    from backend.db import get_engine

    engine = get_engine()
    res = replay_demo_narrative(engine)
    print(f"Replayed demo narrative successfully: {res}")
