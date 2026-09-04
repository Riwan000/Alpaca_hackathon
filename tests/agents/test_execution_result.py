"""ExecutionResult mapping + fills persistence — task P5-BE-14 / issue #137.

Confirms:
- every Alpaca *terminal* order state maps to the right
  :class:`~backend.models.enums.ExecutionStatus`; a live/non-terminal state
  raises rather than fabricating a result;
- ``build_execution_result`` turns a filled combo order into a ``FILLED``
  result with per-leg realized prices and slippage;
- ``persist_execution_result`` writes the ``orders`` row and one ``fills`` row
  per filled leg, prices intact.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine

from backend.agents.execution import (
    ExecutionResultError,
    build_execution_result,
    map_broker_status,
    persist_execution_result,
)
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.orders_repo import OrderRepository
from backend.models.enums import ExecutionStatus
from backend.models.execution import ExecutionPlan

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

_LONG = "AAPL261003P00145000"
_SHORT = "AAPL261003P00140000"


def _plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "cycle_id": "cyc-result",
            "approval_id": "risk-cyc-result",
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


def _leg(symbol: str, side: str, filled_qty: int, price: str, status: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "side": side,
        "qty": "2",
        "filled_qty": str(filled_qty),
        "filled_avg_price": price if filled_qty else "",
        "status": status,
        "filled_at": "2026-09-03T14:35:01Z",
    }


@pytest.mark.parametrize(
    ("broker_status", "expected"),
    [
        ("filled", ExecutionStatus.FILLED),
        ("partially_filled", ExecutionStatus.PARTIALLY_FILLED),
        ("canceled", ExecutionStatus.CANCELLED),
        ("cancelled", ExecutionStatus.CANCELLED),
        ("expired", ExecutionStatus.CANCELLED),
        ("rejected", ExecutionStatus.FAILED),
    ],
)
def test_map_broker_status_terminal_states(broker_status: str, expected: ExecutionStatus) -> None:
    assert map_broker_status(broker_status) is expected


@pytest.mark.parametrize("live_status", ["new", "accepted", "pending_new", "held", "bogus"])
def test_map_broker_status_rejects_non_terminal(live_status: str) -> None:
    with pytest.raises(ExecutionResultError):
        map_broker_status(live_status)


def test_filled_combo_maps_to_filled_with_prices_and_slippage() -> None:
    broker_order = {
        "id": "combo-9",
        "status": "filled",
        "submitted_at": "2026-09-03T14:35:00Z",
        "filled_at": "2026-09-03T14:35:02Z",
        "legs": [
            _leg(_LONG, "buy", 2, "3.20", "filled"),
            _leg(_SHORT, "sell", 2, "1.90", "filled"),
        ],
    }
    result = build_execution_result(_plan(), broker_order)

    assert result.status is ExecutionStatus.FILLED
    assert result.broker_order_id == "combo-9"
    prices = {fl.leg_symbol: fl.price for fl in result.filled_legs}
    assert prices == {_LONG: pytest.approx(3.20), _SHORT: pytest.approx(1.90)}
    slip = {fl.leg_symbol: fl.slippage for fl in result.filled_legs}
    assert slip[_LONG] == pytest.approx(0.05)
    assert slip[_SHORT] == pytest.approx(-0.05)
    # |3.20*2*100 - 1.90*2*100|
    assert result.actual_cost == pytest.approx(260.0)


def test_no_fill_cancelled_order_maps_to_cancelled() -> None:
    broker_order = {
        "id": "combo-10",
        "status": "canceled",
        "legs": [
            _leg(_LONG, "buy", 0, "", "canceled"),
            _leg(_SHORT, "sell", 0, "", "canceled"),
        ],
    }
    result = build_execution_result(_plan(), broker_order)
    assert result.status is ExecutionStatus.CANCELLED
    assert not result.filled_legs
    assert result.error is None


def test_rejected_order_maps_to_failed_with_error() -> None:
    broker_order = {
        "id": "combo-11",
        "status": "rejected",
        "reject_reason": "buying power exceeded",
        "legs": [
            _leg(_LONG, "buy", 0, "", "rejected"),
            _leg(_SHORT, "sell", 0, "", "rejected"),
        ],
    }
    result = build_execution_result(_plan(), broker_order)
    assert result.status is ExecutionStatus.FAILED
    assert result.error == "buying power exceeded"


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #


@pytest.fixture
def _migrated_engine(tmp_path: Path) -> Iterator[Any]:
    db_url = f"sqlite:///{tmp_path / 'exec_result_scratch.db'}"
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    yield engine
    engine.dispose()


@pytest.mark.integration
def test_persist_execution_result_writes_order_and_fills(_migrated_engine: Any) -> None:
    broker_order = {
        "id": "combo-9",
        "status": "filled",
        "legs": [
            _leg(_LONG, "buy", 2, "3.20", "filled"),
            _leg(_SHORT, "sell", 2, "1.90", "filled"),
        ],
    }
    plan = _plan()
    result = build_execution_result(plan, broker_order)

    saved = persist_execution_result(_migrated_engine, plan, result)

    repo = OrderRepository(_migrated_engine)
    assert repo.count() == 1
    assert repo.count_fills() == 2

    stored = repo.get_with_fills(saved.order.id)
    assert stored is not None
    assert stored.order.status == "FILLED"
    assert stored.order.cycle_id == "cyc-result"
    assert stored.order.broker_order_id == "combo-9"
    prices = sorted(float(f.price) for f in stored.fills)
    assert prices == pytest.approx([1.90, 3.20])
    assert all(f.slippage is not None for f in stored.fills)
