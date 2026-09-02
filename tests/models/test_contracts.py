"""Round-trip contract tests — tasks P1-BE-9 … P1-BE-13.

Each contract: a good raw fixture validates, at least one bad variant is
rejected, and ``model_validate(model_dump())`` / ``model_validate_json(
model_dump_json())`` both reproduce an equal instance.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from backend.models import (
    ExecutionPlan,
    ExecutionResult,
    HedgeContext,
    MonitoringState,
    RiskDecision,
    StrategyDecision,
    StrategyHypothesis,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _assert_roundtrips(model: BaseModel) -> None:
    cls = type(model)
    assert cls.model_validate(model.model_dump()) == model
    assert cls.model_validate_json(model.model_dump_json()) == model


def _without(fixture: dict[str, Any], key: str) -> dict[str, Any]:
    out = copy.deepcopy(fixture)
    out.pop(key)
    return out


def _with(fixture: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    out = copy.deepcopy(fixture)
    out.update(overrides)
    return out


# --------------------------------------------------------------------------- #
# fixtures (raw, JSON-shaped)
# --------------------------------------------------------------------------- #

HYPOTHESIS_FIXTURE: dict[str, Any] = {
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

NO_HEDGE_HYPOTHESIS_FIXTURE: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "strategy": "NO_HEDGE",
    "action": "NO_TRADE",
    "viable": True,
    "cost": 0.0,
    "rationale": "Drawdown is inside tolerance; protection is not worth the carry.",
}

HEDGE_CONTEXT_FIXTURE: dict[str, Any] = {
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

STRATEGY_DECISION_FIXTURE: dict[str, Any] = {
    "cycle_id": "cyc-001",
    "decision": "SELECT_STRATEGY",
    "selected_strategy": "PROTECTIVE_PUT",
    "selected_hypothesis": HYPOTHESIS_FIXTURE,
    "alternatives": [NO_HEDGE_HYPOTHESIS_FIXTURE],
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

RISK_DECISION_FIXTURE: dict[str, Any] = {
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
    "approved_hypothesis": HYPOTHESIS_FIXTURE,
}

EXECUTION_PLAN_FIXTURE: dict[str, Any] = {
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

EXECUTION_RESULT_FIXTURE: dict[str, Any] = {
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

MONITORING_STATE_FIXTURE: dict[str, Any] = {
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


# --------------------------------------------------------------------------- #
# P1-BE-9 — HedgeContext
# --------------------------------------------------------------------------- #


def test_hedge_context_roundtrip() -> None:
    ctx = HedgeContext.model_validate(HEDGE_CONTEXT_FIXTURE)
    assert ctx.cycle_id == "cyc-001"
    assert ctx.portfolio_state.positions[0].symbol == "AAPL"
    assert ctx.current_hedge.active is False
    _assert_roundtrips(ctx)

    # missing a required section
    with pytest.raises(ValidationError):
        HedgeContext.model_validate(_without(HEDGE_CONTEXT_FIXTURE, "portfolio_state"))

    # an unknown key is rejected, not silently dropped
    with pytest.raises(ValidationError):
        HedgeContext.model_validate(_with(HEDGE_CONTEXT_FIXTURE, unexpected_field=1))

    # a bounded metric out of range
    bad = copy.deepcopy(HEDGE_CONTEXT_FIXTURE)
    bad["portfolio_state"]["concentration_hhi"] = 1.5
    with pytest.raises(ValidationError):
        HedgeContext.model_validate(bad)


# --------------------------------------------------------------------------- #
# P1-BE-10 — StrategyHypothesis / StrategyDecision
# --------------------------------------------------------------------------- #


def test_strategy_roundtrip() -> None:
    hyp = StrategyHypothesis.model_validate(HYPOTHESIS_FIXTURE)
    decision = StrategyDecision.model_validate(STRATEGY_DECISION_FIXTURE)
    assert decision.selected_hypothesis == hyp
    _assert_roundtrips(hyp)
    _assert_roundtrips(decision)

    # enum fields reject unknown values
    with pytest.raises(ValidationError):
        StrategyHypothesis.model_validate(_with(HYPOTHESIS_FIXTURE, strategy="WING_SPREAD"))
    with pytest.raises(ValidationError):
        StrategyHypothesis.model_validate(_with(HYPOTHESIS_FIXTURE, action="YOLO"))
    with pytest.raises(ValidationError):
        StrategyDecision.model_validate(_with(STRATEGY_DECISION_FIXTURE, decision="MAYBE"))

    # a non-viable hypothesis must explain itself
    with pytest.raises(ValidationError):
        StrategyHypothesis.model_validate(_with(HYPOTHESIS_FIXTURE, viable=False))

    non_viable = _with(
        HYPOTHESIS_FIXTURE, viable=False, rejection_reason="premium is 3.1% of the portfolio"
    )
    _assert_roundtrips(StrategyHypothesis.model_validate(non_viable))

    # SELECT_STRATEGY without a selection is incoherent
    with pytest.raises(ValidationError):
        StrategyDecision.model_validate(_without(STRATEGY_DECISION_FIXTURE, "selected_hypothesis"))

    # a NO_TRADE decision needs no selection
    no_trade = {
        "cycle_id": "cyc-001",
        "decision": "NO_TRADE",
        "rationale": "Every hypothesis was NOT_VIABLE.",
    }
    _assert_roundtrips(StrategyDecision.model_validate(no_trade))


# --------------------------------------------------------------------------- #
# P1-BE-11 — RiskDecision
# --------------------------------------------------------------------------- #


def test_risk_decision_roundtrip() -> None:
    decision = RiskDecision.model_validate(RISK_DECISION_FIXTURE)
    assert decision.verdict.value == "APPROVE"
    _assert_roundtrips(decision)

    # unknown verdict rejected
    with pytest.raises(ValidationError):
        RiskDecision.model_validate(_with(RISK_DECISION_FIXTURE, verdict="DENY"))

    # a REJECT with no violation, and a MODIFY with no modification, are incoherent
    with pytest.raises(ValidationError):
        RiskDecision.model_validate(_with(RISK_DECISION_FIXTURE, verdict="REJECT"))
    with pytest.raises(ValidationError):
        RiskDecision.model_validate(_with(RISK_DECISION_FIXTURE, verdict="MODIFY"))

    reject = _with(
        RISK_DECISION_FIXTURE,
        verdict="REJECT",
        violations=["cost 6.2% exceeds the 5% hard budget"],
        approved_hypothesis=None,
    )
    _assert_roundtrips(RiskDecision.model_validate(reject))

    modify = _with(
        RISK_DECISION_FIXTURE,
        verdict="MODIFY",
        modifications=[
            {"field": "quantity", "from_value": 30, "to_value": 20, "reason": "cap notional"}
        ],
    )
    _assert_roundtrips(RiskDecision.model_validate(modify))


# --------------------------------------------------------------------------- #
# P1-BE-12 — ExecutionPlan / ExecutionResult
# --------------------------------------------------------------------------- #


def test_execution_roundtrip() -> None:
    plan = ExecutionPlan.model_validate(EXECUTION_PLAN_FIXTURE)
    assert len(plan.legs) == 2
    result = ExecutionResult.model_validate(EXECUTION_RESULT_FIXTURE)
    assert result.status.value == "FILLED"
    _assert_roundtrips(plan)
    _assert_roundtrips(result)

    # result status is enum-bound
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(_with(EXECUTION_RESULT_FIXTURE, status="DONE"))

    # a multi-leg plan cannot be submitted as independent single orders
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(_with(EXECUTION_PLAN_FIXTURE, order_class="SINGLE"))

    # an empty-leg plan is rejected
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(_with(EXECUTION_PLAN_FIXTURE, legs=[]))

    # a partial fill must be reported truthfully, never as FILLED
    partial = _with(
        EXECUTION_RESULT_FIXTURE,
        status="PARTIALLY_FILLED",
        filled_legs=[EXECUTION_RESULT_FIXTURE["filled_legs"][0]],
        failed_legs=[{"leg_symbol": "SPY261218P00470000", "reason": "no bid at limit"}],
    )
    _assert_roundtrips(ExecutionResult.model_validate(partial))

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(_with(EXECUTION_RESULT_FIXTURE, status="PARTIALLY_FILLED"))


# --------------------------------------------------------------------------- #
# P1-BE-13 — MonitoringState
# --------------------------------------------------------------------------- #


def test_monitoring_state_roundtrip() -> None:
    state = MonitoringState.model_validate(MONITORING_STATE_FIXTURE)
    assert [t.trigger_type.value for t in state.trigger_history] == [
        "DRAWDOWN_LIMIT",
        "VOLATILITY_SPIKE",
    ]
    # cooldown_until is optional
    assert state.cooldown_until is None
    assert state.in_cooldown is False
    _assert_roundtrips(state)

    # trigger_history is typed — an unknown trigger type is rejected
    bad_type = copy.deepcopy(MONITORING_STATE_FIXTURE)
    bad_type["trigger_history"][0]["trigger_type"] = "MOON_PHASE"
    with pytest.raises(ValidationError):
        MonitoringState.model_validate(bad_type)

    # trigger_history is typed — a required field on an entry is enforced
    missing_field = copy.deepcopy(MONITORING_STATE_FIXTURE)
    missing_field["trigger_history"][0].pop("trigger_type")
    with pytest.raises(ValidationError):
        MonitoringState.model_validate(missing_field)

    # cooldown_until present + in_cooldown set round-trips
    cooling = _with(
        MONITORING_STATE_FIXTURE,
        cooldown_until="2026-09-03T15:05:00Z",
        in_cooldown=True,
    )
    _assert_roundtrips(MonitoringState.model_validate(cooling))

    # in_cooldown without a cooldown_until is incoherent
    with pytest.raises(ValidationError):
        MonitoringState.model_validate(_with(MONITORING_STATE_FIXTURE, in_cooldown=True))
