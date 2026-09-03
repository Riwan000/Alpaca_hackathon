"""``orders`` + ``fills`` repository tests — tasks P5-DB-2, P5-DB-3.

Flow under test: a submitted hedge persists as one ``orders`` row with its
``legs``, then N ``fills`` rows linked to it by ``order_id``. The order's
``status`` only ever moves forward through the lifecycle.

- ``save_with_fills`` writes the order + its legs and links the fills;
- ``fills_for`` reads them back in order; the FK is enforced;
- ``update_status`` accepts a forward transition and rejects a backward one
  (``test_status_transitions_are_monotonic``);
- ``test_slippage`` — ``record_fill`` computes ``slippage = price -
  expected_price``; a failed submit writes an ``execution_failures`` row.
"""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.execution_failures_repo import (
    ExecutionFailureRecord,
    ExecutionFailureRepository,
)
from backend.db.orders_repo import (
    FillRecord,
    MonotonicStatusError,
    OrderRecord,
    OrderRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'orders_scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def engine(tmp_path: Path):
    db_url = _scratch_url(tmp_path)
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    eng = create_engine(normalize_driver(db_url))
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def repo(engine) -> OrderRepository:
    return OrderRepository(engine)


def _combo_order(cycle_id: str) -> OrderRecord:
    return OrderRecord(
        cycle_id=cycle_id,
        order_class="MLEG",
        status="SUBMITTED",
        legs=[
            {"symbol": "AAPL260320P00145000", "side": "BUY", "ratio": 1},
            {"symbol": "AAPL260320P00135000", "side": "SELL", "ratio": 1},
        ],
        broker_order_id="alpaca-combo-1",
    )


def test_order_persists_with_legs_and_fills_link_to_it(repo: OrderRepository) -> None:
    """P5-DB-2: order + legs land; fills carry the order's id."""
    cycle = "cycle_p5_db_2"
    result = repo.save_with_fills(
        _combo_order(cycle),
        [
            FillRecord(order_id=0, leg_symbol="AAPL260320P00145000", qty=Decimal("1"), price=Decimal("3.15")),
            FillRecord(order_id=0, leg_symbol="AAPL260320P00135000", qty=Decimal("1"), price=Decimal("1.05")),
        ],
    )

    assert result.order.id is not None
    assert result.order.legs[0]["symbol"] == "AAPL260320P00145000"
    assert repo.count() == 1
    assert repo.count_fills() == 2
    assert all(f.order_id == result.order.id for f in result.fills)

    reloaded = repo.get_with_fills(result.order.id)
    assert reloaded is not None
    assert [f.leg_symbol for f in reloaded.fills] == [
        "AAPL260320P00145000",
        "AAPL260320P00135000",
    ]
    assert reloaded.order.legs == result.order.legs


def test_fill_for_a_missing_order_is_refused_by_the_fk(repo: OrderRepository) -> None:
    with pytest.raises(LookupError):
        repo.add_fill(
            FillRecord(order_id=999, leg_symbol="X", qty=Decimal("1"), price=Decimal("1"))
        )
    assert repo.count_fills() == 0


def test_status_transitions_are_monotonic(repo: OrderRepository) -> None:
    """P5-DB-2: status moves forward only."""
    order = repo.create(OrderRecord(cycle_id="cycle_s", order_class="MLEG", status="PENDING"))
    assert order.id is not None

    assert repo.update_status(order.id, "SUBMITTED").status == "SUBMITTED"
    assert repo.update_status(order.id, "PARTIALLY_FILLED").status == "PARTIALLY_FILLED"
    assert repo.update_status(order.id, "FILLED").status == "FILLED"

    # backward — FILLED -> PARTIALLY_FILLED — is rejected.
    with pytest.raises(MonotonicStatusError):
        repo.update_status(order.id, "PARTIALLY_FILLED")
    # leaving a terminal state is rejected.
    with pytest.raises(MonotonicStatusError):
        repo.update_status(order.id, "CANCELLED")
    # unchanged in the DB.
    assert repo.get(order.id).status == "FILLED"


def test_status_backward_from_submitted_is_rejected(repo: OrderRepository) -> None:
    order = repo.create(OrderRecord(cycle_id="cycle_s2", order_class="MLEG", status="SUBMITTED"))
    with pytest.raises(MonotonicStatusError):
        repo.update_status(order.id, "PENDING")


def test_list_for_cycle_does_not_bleed(repo: OrderRepository) -> None:
    repo.create(OrderRecord(cycle_id="cycle_a", order_class="MLEG", status="SUBMITTED"))
    repo.create(OrderRecord(cycle_id="cycle_a", order_class="SINGLE", status="PENDING"))
    repo.create(OrderRecord(cycle_id="cycle_b", order_class="MLEG", status="SUBMITTED"))

    assert len(repo.list_for_cycle("cycle_a")) == 2
    assert len(repo.list_for_cycle("cycle_b")) == 1
    assert len(repo.list_all()) == 3


def test_slippage(repo: OrderRepository, engine) -> None:
    """P5-DB-3: slippage = fill price - expected price; a failed submit writes a row."""
    order = repo.create(_combo_order("cycle_p5_db_3"))
    assert order.id is not None

    long_leg = repo.record_fill(
        order.id,
        leg_symbol="AAPL260320P00145000",
        qty=Decimal("1"),
        price=Decimal("3.20"),
        expected_price=Decimal("3.15"),
    )
    short_leg = repo.record_fill(
        order.id,
        leg_symbol="AAPL260320P00135000",
        qty=Decimal("1"),
        price=Decimal("1.00"),
        expected_price=Decimal("1.05"),
    )

    assert long_leg.slippage == Decimal("0.0500")
    assert short_leg.slippage == Decimal("-0.0500")

    # Confirm query: `select leg_symbol, slippage from fills` is populated.
    with engine.connect() as conn:
        rows = conn.execute(
            text("select leg_symbol, slippage from fills order by id")
        ).all()
    slippage_by_leg = {r[0]: Decimal(str(r[1])) for r in rows}
    assert slippage_by_leg["AAPL260320P00145000"] == Decimal("0.05")
    assert slippage_by_leg["AAPL260320P00135000"] == Decimal("-0.05")

    # A fill with no expected price stores NULL slippage.
    bare = repo.record_fill(
        order.id, leg_symbol="AAPL260320P00145000", qty=Decimal("1"), price=Decimal("3.10")
    )
    assert bare.slippage is None

    # A failed submit writes an execution_failures row (no order/fill invented).
    failures = ExecutionFailureRepository(engine)
    failures.create(
        ExecutionFailureRecord(
            cycle_id="cycle_p5_db_3",
            order_id=order.id,
            stage="SUBMIT",
            reason="broker rejected combo order: insufficient buying power",
            detail={"buying_power": 1200.0, "required": 3150.0},
        )
    )
    recorded = failures.list_for_cycle("cycle_p5_db_3")
    assert len(recorded) == 1
    assert recorded[0].stage == "SUBMIT"
    assert recorded[0].order_id == order.id
    assert "buying power" in recorded[0].reason


def test_execution_failure_before_any_order_has_null_order_id(engine) -> None:
    failures = ExecutionFailureRepository(engine)
    row = failures.create(
        ExecutionFailureRecord(
            cycle_id="cycle_preflight",
            stage="PREFLIGHT",
            reason="quote is stale; mid drifted 6% since approval",
        )
    )
    assert row.order_id is None
    assert failures.list_for_cycle("cycle_preflight")[0].order_id is None
