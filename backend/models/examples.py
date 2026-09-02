"""Canonical example instances of every agent-state contract — task P1-BE-15.

One validated instance per contract, shared by the stub routers
(:mod:`backend.api.stubs`), the OpenAPI examples, and the contract round-trip
test (:mod:`tests.test_contracts_roundtrip`). Building them by validating a raw
dict keeps the examples honest — they exercise the same validators the wire
payloads do, so an example can never drift out of spec without a test failing.
"""

from __future__ import annotations

from typing import Any

from backend.models.execution import ExecutionPlan, ExecutionResult
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState
from backend.models.risk import RiskDecision
from backend.models.strategy import StrategyDecision, StrategyHypothesis

__all__ = [
    "EXAMPLE_HEDGE_CONTEXT",
    "EXAMPLE_STRATEGY_HYPOTHESIS",
    "EXAMPLE_STRATEGY_DECISION",
    "EXAMPLE_RISK_DECISION",
    "EXAMPLE_EXECUTION_PLAN",
    "EXAMPLE_EXECUTION_RESULT",
    "EXAMPLE_MONITORING_STATE",
    "EXAMPLES_BY_CONTRACT",
]

_HYPOTHESIS_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "strategy": "PROTECTIVE_PUT",
    "action": "NEW_HEDGE",
    "viable": True,
    "legs": [
        {
            "underlying": "SPY",
            "right": "PUT",
            "side": "BUY",
            "strike": 500.0,
            "expiration": "2026-12-18",
            "quantity": 20,
            "limit_price": 8.5,
        }
    ],
    "cost": 17000.0,
    "hedge_metrics": {
        "hedge_ratio": 0.2,
        "downside_protection_pct": 0.9,
        "cost_pct_of_portfolio": 0.017,
        "net_delta": -700.0,
        "max_loss": 17000.0,
        "breakevens": [491.5],
    },
    "payoff_profile": [
        {"price": 400.0, "pnl": -17000.0},
        {"price": 500.0, "pnl": -17000.0},
        {"price": 600.0, "pnl": 83000.0},
    ],
    "liquidity": "OK",
    "risks": ["negative carry"],
    "tradeoffs": ["premium drag on flat tape"],
    "rationale": "Direct downside protection within the hedge budget.",
    "rejection_conditions": ["premium exceeds 2% of portfolio value"],
}

_NO_HEDGE_HYPOTHESIS_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "strategy": "NO_HEDGE",
    "action": "NO_TRADE",
    "viable": True,
    "cost": 0.0,
    "rationale": "Drawdown is inside tolerance; protection is not worth the carry.",
}

_HEDGE_CONTEXT_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "timestamp": "2026-09-03T14:30:00Z",
    "portfolio_state": {
        "total_value": 1_000_000.0,
        "cash": 200_000.0,
        "equity": 800_000.0,
        "buying_power": 400_000.0,
        "positions": [
            {
                "symbol": "AAPL",
                "qty": 1000.0,
                "avg_price": 150.0,
                "market_value": 180_000.0,
                "asset_class": "EQUITY",
                "side": "BUY",
                "unrealized_pl": 30_000.0,
            }
        ],
        "gross_exposure": 800_000.0,
        "net_exposure": 760_000.0,
        "concentration_hhi": 0.42,
        "drawdown": -0.07,
        "max_drawdown": -0.12,
        "volatility": 0.19,
        "beta": 1.1,
    },
    "objective": {
        "max_hedge_budget_pct": 0.05,
        "drawdown_tolerance_pct": 0.1,
        "target_hedge_ratio": 0.2,
        "notes": "capital preservation into year end",
    },
    "market_state": {
        "regime": "RISK_OFF",
        "index_trend": "DOWN",
        "vix": 24.5,
        "as_of": "2026-09-03T14:00:00Z",
    },
    "stock_state": [
        {
            "symbol": "AAPL",
            "risk_note": "earnings in 3 weeks; elevated single-name risk",
            "momentum": -0.3,
            "key_levels": [140.0, 160.0],
        }
    ],
    "news_context": [
        {
            "headline": "Fed holds rates, signals caution",
            "ts": "2026-09-03T12:00:00Z",
            "symbols": ["SPY"],
            "source": "reuters",
            "sentiment": -0.2,
            "is_event": True,
        }
    ],
    "option_candidates": [
        {
            "underlying": "SPY",
            "right": "PUT",
            "strike": 500.0,
            "expiration": "2026-12-18",
            "premium": 8.5,
            "bid": 8.4,
            "ask": 8.6,
            "volume": 1200,
            "open_interest": 5000,
            "iv": 0.21,
            "delta": -0.35,
            "gamma": 0.01,
            "theta": -0.04,
            "vega": 0.9,
            "liquidity": "OK",
        }
    ],
    "current_hedge": {"active": False},
    "degraded_sections": [],
}

_STRATEGY_DECISION_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "decision": "SELECT_STRATEGY",
    "selected_strategy": "PROTECTIVE_PUT",
    "selected_hypothesis": _HYPOTHESIS_RAW,
    "alternatives": [_NO_HEDGE_HYPOTHESIS_RAW],
    "comparison": [
        {
            "strategy": "PROTECTIVE_PUT",
            "cost": 17000.0,
            "downside_protection_pct": 0.9,
            "upside_giveup_pct": 0.0,
            "liquidity": "OK",
            "verdict": "SELECTED",
            "score": 0.82,
        },
        {
            "strategy": "NO_HEDGE",
            "cost": 0.0,
            "downside_protection_pct": 0.0,
            "verdict": "REJECTED",
            "score": 0.4,
        },
    ],
    "rationale": "Protective put gives the most protection per dollar within budget.",
    "reassessment_conditions": ["drawdown recovers past -3%", "VIX falls below 18"],
}

_RISK_DECISION_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "verdict": "APPROVE",
    "checks": [
        {"name": "hedge_budget", "category": "COST", "passed": True, "observed": 0.017, "limit": 0.05},
        {
            "name": "max_hedge_ratio",
            "category": "POSITION_LIMITS",
            "passed": True,
            "observed": 0.2,
            "limit": 0.35,
        },
        {"name": "buying_power", "category": "EXECUTION", "passed": True},
    ],
    "violations": [],
    "warnings": ["IV is elevated vs its 30-day average"],
    "modifications": [],
    "rationale": "Every deterministic check passes and the plan is inside budget.",
    "approved_hypothesis": _HYPOTHESIS_RAW,
}

_EXECUTION_PLAN_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "approval_id": "risk-cyc-001",
    "strategy": "PUT_SPREAD",
    "legs": [
        {
            "underlying": "SPY",
            "right": "PUT",
            "side": "BUY",
            "strike": 500.0,
            "expiration": "2026-12-18",
            "quantity": 20,
            "limit_price": 8.5,
        },
        {
            "underlying": "SPY",
            "right": "PUT",
            "side": "SELL",
            "strike": 470.0,
            "expiration": "2026-12-18",
            "quantity": 20,
            "limit_price": 3.2,
        },
    ],
    "order_class": "MLEG",
    "constraints": {
        "time_in_force": "DAY",
        "order_type": "LIMIT",
        "limit_price": 5.3,
        "price_tolerance_pct": 0.05,
        "allow_legging": False,
    },
    "estimated_cost": 10_600.0,
}

_EXECUTION_RESULT_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "status": "FILLED",
    "order_ids": ["abc-123"],
    "broker_order_id": "abc-123",
    "filled_legs": [
        {
            "leg_symbol": "SPY261218P00500000",
            "qty": 20,
            "price": 8.55,
            "filled_at": "2026-09-03T14:35:01Z",
            "slippage": 0.05,
        },
        {
            "leg_symbol": "SPY261218P00470000",
            "qty": 20,
            "price": 3.18,
            "filled_at": "2026-09-03T14:35:01Z",
            "slippage": -0.02,
        },
    ],
    "failed_legs": [],
    "actual_cost": 10_740.0,
    "slippage": 0.03,
    "submitted_at": "2026-09-03T14:35:00Z",
    "completed_at": "2026-09-03T14:35:02Z",
}

_MONITORING_STATE_RAW: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "as_of": "2026-09-03T15:00:00Z",
    "portfolio_value": 995_000.0,
    "drawdown": -0.065,
    "volatility": 0.2,
    "gross_exposure": 800_000.0,
    "hedge_ratio": 0.19,
    "target_hedge_ratio": 0.2,
    "hedge_pnl": 1_200.0,
    "time_to_expiration_days": 88.5,
    "trigger_history": [
        {
            "trigger_type": "DRAWDOWN_LIMIT",
            "observed_at": "2026-09-03T14:00:00Z",
            "observed_value": -0.07,
            "threshold": -0.05,
            "detail": "drawdown exceeded the configured limit",
            "breached": True,
        },
        {
            "trigger_type": "VOLATILITY_SPIKE",
            "observed_at": "2026-09-03T14:30:00Z",
            "observed_value": 0.2,
            "threshold": 0.25,
            "breached": False,
        },
    ],
    "active_triggers": ["DRAWDOWN_LIMIT"],
    "reassessment_recommended": True,
}


EXAMPLE_STRATEGY_HYPOTHESIS: StrategyHypothesis = StrategyHypothesis.model_validate(_HYPOTHESIS_RAW)
EXAMPLE_HEDGE_CONTEXT: HedgeContext = HedgeContext.model_validate(_HEDGE_CONTEXT_RAW)
EXAMPLE_STRATEGY_DECISION: StrategyDecision = StrategyDecision.model_validate(_STRATEGY_DECISION_RAW)
EXAMPLE_RISK_DECISION: RiskDecision = RiskDecision.model_validate(_RISK_DECISION_RAW)
EXAMPLE_EXECUTION_PLAN: ExecutionPlan = ExecutionPlan.model_validate(_EXECUTION_PLAN_RAW)
EXAMPLE_EXECUTION_RESULT: ExecutionResult = ExecutionResult.model_validate(_EXECUTION_RESULT_RAW)
EXAMPLE_MONITORING_STATE: MonitoringState = MonitoringState.model_validate(_MONITORING_STATE_RAW)

# Contract class -> its canonical example instance. Keyed by class so callers
# (stubs, tests) stay in lock-step with ``backend.models.CONTRACT_MODELS``.
EXAMPLES_BY_CONTRACT: dict[type, Any] = {
    HedgeContext: EXAMPLE_HEDGE_CONTEXT,
    StrategyHypothesis: EXAMPLE_STRATEGY_HYPOTHESIS,
    StrategyDecision: EXAMPLE_STRATEGY_DECISION,
    RiskDecision: EXAMPLE_RISK_DECISION,
    ExecutionPlan: EXAMPLE_EXECUTION_PLAN,
    ExecutionResult: EXAMPLE_EXECUTION_RESULT,
    MonitoringState: EXAMPLE_MONITORING_STATE,
}
