"""Legging-risk / partial-fill recovery — task P5-BE-13 / issue #136.

Confirms the Execution Agent never reports a partial fill as success:

- one leg fills and one does not → status is ``PARTIALLY_FILLED`` (never
  ``FILLED``), the unfilled leg is in ``failed_legs``, and a ``recovery_action``
  is recorded;
- a filled short leg left naked by an unfilled long leg → the recovery action is
  to unwind the filled leg, not merely cancel the rest.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.agents.execution import (
    RECOVERY_CANCEL_UNFILLED_LEGS,
    RECOVERY_UNWIND_FILLED_LEGS,
    build_execution_result,
)
from backend.models.enums import ExecutionStatus
from backend.models.execution import ExecutionPlan

_LONG = "AAPL261003P00145000"
_SHORT = "AAPL261003P00140000"


def _plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "cycle_id": "cyc-partial",
            "approval_id": "risk-cyc-partial",
            "strategy": "PUT_SPREAD",
            "legs": [
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "side": "BUY",
                    "strike": 145.0,
                    "expiration": "2026-10-03",
                    "quantity": 2,
                    "limit_price": 3.15,
                },
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "side": "SELL",
                    "strike": 140.0,
                    "expiration": "2026-10-03",
                    "quantity": 2,
                    "limit_price": 1.95,
                },
            ],
            "order_class": "MLEG",
            "constraints": {"limit_price": 1.2},
            "estimated_cost": 240.0,
        }
    )


def _broker_order(long_fill: float, short_fill: float, **leg_prices: float) -> dict[str, Any]:
    return {
        "id": "combo-1",
        "status": "partially_filled",
        "submitted_at": "2026-09-03T14:35:00Z",
        "filled_at": "2026-09-03T14:35:02Z",
        "legs": [
            {
                "symbol": _LONG,
                "side": "buy",
                "qty": "2",
                "filled_qty": str(long_fill),
                "filled_avg_price": str(leg_prices.get("long_price", 3.20)) if long_fill else "",
                "status": "filled" if long_fill >= 2 else ("partially_filled" if long_fill else "canceled"),
                "filled_at": "2026-09-03T14:35:01Z",
            },
            {
                "symbol": _SHORT,
                "side": "sell",
                "qty": "2",
                "filled_qty": str(short_fill),
                "filled_avg_price": str(leg_prices.get("short_price", 1.90)) if short_fill else "",
                "status": "filled" if short_fill >= 2 else ("partially_filled" if short_fill else "canceled"),
                "filled_at": "2026-09-03T14:35:01Z",
            },
        ],
    }


def test_one_leg_fills_one_does_not_is_partially_filled() -> None:
    result = build_execution_result(_plan(), _broker_order(long_fill=2, short_fill=0))

    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert result.status is not ExecutionStatus.FILLED
    assert [fl.leg_symbol for fl in result.filled_legs] == [_LONG]
    assert [fl.leg_symbol for fl in result.failed_legs] == [_SHORT]
    assert result.recovery_action  # recorded, non-empty
    assert result.recovery_action == RECOVERY_CANCEL_UNFILLED_LEGS


def test_partial_fill_records_slippage_on_the_filled_leg() -> None:
    result = build_execution_result(
        _plan(), _broker_order(long_fill=2, short_fill=0, long_price=3.20)
    )
    (filled,) = result.filled_legs
    assert filled.slippage == pytest.approx(0.05)  # 3.20 realized vs 3.15 expected


def test_naked_short_leg_recovery_is_unwind_not_cancel() -> None:
    """Short leg filled, long protection did not → unwind the naked short."""
    result = build_execution_result(_plan(), _broker_order(long_fill=0, short_fill=2))

    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert [fl.leg_symbol for fl in result.filled_legs] == [_SHORT]
    assert [fl.leg_symbol for fl in result.failed_legs] == [_LONG]
    assert result.recovery_action == RECOVERY_UNWIND_FILLED_LEGS


def test_clean_fill_reports_no_recovery_needed() -> None:
    result = build_execution_result(_plan(), _broker_order(long_fill=2, short_fill=2))
    assert result.status is ExecutionStatus.FILLED
    assert result.recovery_action == "NONE"
    assert not result.failed_legs
