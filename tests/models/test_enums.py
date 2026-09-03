"""Shared-enum tests — task P1-BE-14.

Pins every member name *and* its string value. A rename or a value drift breaks
one of these, which is the point: the DB enum types (``order_status_enum``,
``trigger_type_enum``) and the frontend TS unions are generated against these
tokens.
"""

from __future__ import annotations

import pytest

from backend.models.enums import (
    AssetClass,
    DecisionType,
    ExecutionStatus,
    HedgeAction,
    MarketRegime,
    OptionRight,
    OrderSide,
    OrderStatus,
    RiskVerdict,
    StrategyType,
    TriggerType,
)

# name -> pinned string value, per enum
PINNED: dict[type, dict[str, str]] = {
    StrategyType: {
        "PROTECTIVE_PUT": "PROTECTIVE_PUT",
        "PUT_SPREAD": "PUT_SPREAD",
        "COLLAR": "COLLAR",
        "NO_HEDGE": "NO_HEDGE",
    },
    HedgeAction: {
        "NEW_HEDGE": "NEW_HEDGE",
        "INCREASE": "INCREASE",
        "DECREASE": "DECREASE",
        "MAINTAIN": "MAINTAIN",
        "REMOVE": "REMOVE",
        "REPLACE": "REPLACE",
        "NO_TRADE": "NO_TRADE",
    },
    DecisionType: {
        "SELECT_STRATEGY": "SELECT_STRATEGY",
        "NO_TRADE": "NO_TRADE",
        "REASSESS": "REASSESS",
    },
    RiskVerdict: {
        "APPROVE": "APPROVE",
        "MODIFY": "MODIFY",
        "REJECT": "REJECT",
    },
    OrderStatus: {
        "PENDING": "PENDING",
        "SUBMITTED": "SUBMITTED",
        "FILLED": "FILLED",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "CANCELLED": "CANCELLED",
        "EXPIRED": "EXPIRED",
        "REJECTED": "REJECTED",
    },
    ExecutionStatus: {
        "FILLED": "FILLED",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "FAILED": "FAILED",
        "CANCELLED": "CANCELLED",
    },
    TriggerType: {
        "PORTFOLIO_DELTA": "PORTFOLIO_DELTA",
        "VOLATILITY_SPIKE": "VOLATILITY_SPIKE",
        "CORRELATION_BREAKDOWN": "CORRELATION_BREAKDOWN",
        "DRAWDOWN_LIMIT": "DRAWDOWN_LIMIT",
        "TIME_ELAPSED": "TIME_ELAPSED",
        "MANUAL": "MANUAL",
    },
    MarketRegime: {
        "RISK_ON": "RISK_ON",
        "NEUTRAL": "NEUTRAL",
        "RISK_OFF": "RISK_OFF",
        "HIGH_VOL": "HIGH_VOL",
    },
    OptionRight: {"CALL": "CALL", "PUT": "PUT"},
    OrderSide: {"BUY": "BUY", "SELL": "SELL"},
    AssetClass: {"EQUITY": "EQUITY", "OPTION": "OPTION", "CASH": "CASH"},
}


@pytest.mark.parametrize("enum_cls", list(PINNED), ids=lambda c: c.__name__)
def test_members_and_values_pinned(enum_cls: type) -> None:
    expected = PINNED[enum_cls]
    assert {m.name for m in enum_cls} == set(expected)
    for name, value in expected.items():
        assert enum_cls[name].value == value
    # every enum is a str enum, so a member compares equal to its token
    for member in enum_cls:
        assert member == member.value
        assert isinstance(member.value, str)


def test_order_status_documented_set_and_order() -> None:
    """`python -c "from backend.models.enums import *; print(list(OrderStatus))"`."""
    assert [s.value for s in OrderStatus] == [
        "PENDING",
        "SUBMITTED",
        "FILLED",
        "PARTIALLY_FILLED",
        "CANCELLED",
        "EXPIRED",
        "REJECTED",
    ]


def test_trigger_type_matches_migration_enum() -> None:
    # mirrors trigger_type_enum in backend/db/migrations/versions/0010_monitoring_events.py
    assert [t.value for t in TriggerType] == [
        "PORTFOLIO_DELTA",
        "VOLATILITY_SPIKE",
        "CORRELATION_BREAKDOWN",
        "DRAWDOWN_LIMIT",
        "TIME_ELAPSED",
        "MANUAL",
    ]


def test_unknown_value_raises() -> None:
    with pytest.raises(ValueError):
        OrderStatus("NOT_A_STATUS")
    with pytest.raises(ValueError):
        StrategyType("IRON_CONDOR")
