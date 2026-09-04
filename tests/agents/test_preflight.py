"""Pre-flight validation tests — task P5-BE-11 / issue #134.

Confirms that a plan approved earlier is re-checked against a *fresh* context
just before submit, and that any of the following aborts the submit with a
logged reason (and no order sent):

- a leg no longer matches an analyzed contract, or has expired;
- the re-fetched context is stale (older than the staleness limit);
- a leg's mid has drifted past the plan's price-tolerance band since approval;
- the plan's estimated cost no longer fits the account's buying power.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.agents.execution import run_preflight
from backend.models.execution import ExecutionPlan
from backend.models.hedge_context import HedgeContext

_TS = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


def _context(candidates: list[dict[str, Any]] | None = None, *, buying_power: float = 50_000.0) -> HedgeContext:
    default_candidates = [
        {
            "underlying": "AAPL",
            "right": "PUT",
            "strike": 145.0,
            "expiration": "2026-10-03",
            "premium": 3.15,
            "bid": 3.1,
            "ask": 3.2,
            "open_interest": 4200,
        },
        {
            "underlying": "AAPL",
            "right": "PUT",
            "strike": 140.0,
            "expiration": "2026-10-03",
            "premium": 1.95,
            "bid": 1.9,
            "ask": 2.0,
            "open_interest": 3100,
        },
    ]
    return HedgeContext.model_validate(
        {
            "cycle_id": "cyc-preflight",
            "timestamp": _TS.isoformat(),
            "portfolio_state": {
                "total_value": 145_000.0,
                "cash": 100_000.0,
                "equity": 45_000.0,
                "buying_power": buying_power,
                "positions": [],
            },
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "option_candidates": candidates or default_candidates,
        }
    )


def _plan(**overrides: Any) -> ExecutionPlan:
    raw: dict[str, Any] = {
        "cycle_id": "cyc-preflight",
        "approval_id": "risk-cyc-preflight",
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
        "constraints": {"price_tolerance_pct": 0.05},
        "estimated_cost": 2_400.0,
    }
    raw.update(overrides)
    return ExecutionPlan.model_validate(raw)


def test_fresh_context_passes() -> None:
    result = run_preflight(_plan(), _context(), now=_TS + timedelta(minutes=1))
    assert result.ok is True
    assert result.code is None


def test_price_drift_since_approval_aborts_before_submit() -> None:
    """A mid that moved past the band → abort, code PRICE_DRIFT, no order."""
    drifted = _context(
        [
            {
                "underlying": "AAPL",
                "right": "PUT",
                "strike": 145.0,
                "expiration": "2026-10-03",
                "premium": 4.1,
                "bid": 4.0,
                "ask": 4.2,
                "open_interest": 4200,
            },
            {
                "underlying": "AAPL",
                "right": "PUT",
                "strike": 140.0,
                "expiration": "2026-10-03",
                "premium": 1.95,
                "bid": 1.9,
                "ask": 2.0,
                "open_interest": 3100,
            },
        ]
    )
    result = run_preflight(_plan(), drifted, now=_TS + timedelta(minutes=1))
    assert result.ok is False
    assert result.code == "PRICE_DRIFT"
    assert "mid moved" in result.reason


def test_stale_context_aborts() -> None:
    result = run_preflight(
        _plan(),
        _context(),
        now=_TS + timedelta(minutes=30),
        max_quote_age=timedelta(minutes=5),
    )
    assert result.ok is False
    assert result.code == "STALE_QUOTE"


def test_expired_leg_aborts() -> None:
    result = run_preflight(
        _plan(),
        _context(),
        now=datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
    )
    assert result.ok is False
    assert result.code == "CONTRACT_EXPIRED"


def test_unknown_contract_aborts() -> None:
    plan = _plan(
        legs=[
            {
                "underlying": "AAPL",
                "right": "PUT",
                "side": "BUY",
                "strike": 999.0,
                "expiration": "2026-10-03",
                "quantity": 1,
                "limit_price": 3.15,
            }
        ],
        order_class="SINGLE",
    )
    result = run_preflight(plan, _context(), now=_TS + timedelta(minutes=1))
    assert result.ok is False
    assert result.code == "UNKNOWN_CONTRACT"


def test_insufficient_buying_power_aborts() -> None:
    result = run_preflight(
        _plan(estimated_cost=999_999.0),
        _context(buying_power=50_000.0),
        now=_TS + timedelta(minutes=1),
    )
    assert result.ok is False
    assert result.code == "INSUFFICIENT_BUYING_POWER"
