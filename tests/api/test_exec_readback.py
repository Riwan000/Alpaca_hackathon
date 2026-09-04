"""Execution read-back endpoint tests — task P5-DB-4.

* ``GET /risk/checks?cycle_id=`` filters by ``cycle_id``; without it, every row.
* ``GET /orders?cycle_id=`` filters by ``cycle_id`` and each order **includes
  its fills nested**; without it, every order.
* ``GET /execution?cycle_id=`` reshapes the latest order for a cycle into an
  ``ExecutionResult``; 404s when the cycle has no order (a NO_HEDGE decision
  never reaches ``POST /execute``, so that's a legitimate outcome).
* Counts and nested-fill data returned match the database (the P5-DB-4 confirm).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.orders_repo import FillRecord, OrderRecord, OrderRepository
from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


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
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App wired to a migrated scratch DB seeded with two execution cycles."""
    db_url = f"sqlite:///{tmp_path / 'exec_readback_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)

    risk_repo = RiskCheckRepository(engine)
    order_repo = OrderRepository(engine)

    # cycle_a: an APPROVE risk check + a FILLED 2-leg order with two fills.
    risk_repo.create(
        RiskCheckRecord(
            cycle_id="cycle_a",
            verdict="APPROVE",
            checks=[{"name": "hedge_budget", "category": "COST", "passed": True}],
        )
    )
    order_repo.save_with_fills(
        OrderRecord(
            cycle_id="cycle_a",
            order_class="MLEG",
            status="FILLED",
            legs=[
                {"symbol": "AAPL260320P00145000", "side": "BUY"},
                {"symbol": "AAPL260320P00135000", "side": "SELL"},
            ],
            broker_order_id="alpaca-a-1",
        ),
        [
            FillRecord(order_id=0, leg_symbol="AAPL260320P00145000", qty=Decimal("1"), price=Decimal("3.15"), slippage=Decimal("0.02")),
            FillRecord(order_id=0, leg_symbol="AAPL260320P00135000", qty=Decimal("1"), price=Decimal("1.05"), slippage=Decimal("-0.01")),
        ],
    )

    # cycle_b: a REJECT risk check + a REJECTED order with no fills.
    risk_repo.create(
        RiskCheckRecord(
            cycle_id="cycle_b",
            verdict="REJECT",
            violations=["hedge cost exceeds the budget"],
        )
    )
    order_repo.create(
        OrderRecord(cycle_id="cycle_b", order_class="MLEG", status="REJECTED")
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_risk_checks_filtered_by_cycle(client: TestClient) -> None:
    response = client.get("/risk/checks", params={"cycle_id": "cycle_a"})

    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["cycle_id"] == "cycle_a"
    assert rows[0]["verdict"] == "APPROVE"
    assert rows[0]["checks"][0]["name"] == "hedge_budget"


def test_risk_checks_without_cycle_returns_all(client: TestClient) -> None:
    rows = client.get("/risk/checks").json()

    assert len(rows) == 2
    assert {r["verdict"] for r in rows} == {"APPROVE", "REJECT"}
    reject = next(r for r in rows if r["verdict"] == "REJECT")
    assert reject["violations"] == ["hedge cost exceeds the budget"]


def test_orders_filtered_by_cycle_include_nested_fills(client: TestClient) -> None:
    response = client.get("/orders", params={"cycle_id": "cycle_a"})

    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1

    order = rows[0]
    assert order["cycle_id"] == "cycle_a"
    assert order["status"] == "FILLED"
    assert order["order_class"] == "MLEG"
    assert order["broker_order_id"] == "alpaca-a-1"
    assert len(order["fills"]) == 2
    assert [f["leg_symbol"] for f in order["fills"]] == [
        "AAPL260320P00145000",
        "AAPL260320P00135000",
    ]
    assert order["fills"][0]["price"] == 3.15
    assert order["fills"][0]["slippage"] == 0.02
    assert all(f["order_id"] == order["id"] for f in order["fills"])


def test_orders_without_cycle_returns_all_with_fills_key(client: TestClient) -> None:
    rows = client.get("/orders").json()

    assert len(rows) == 2
    by_cycle = {r["cycle_id"]: r for r in rows}
    assert by_cycle["cycle_a"]["fills"]  # the FILLED order has fills
    assert by_cycle["cycle_b"]["fills"] == []  # the REJECTED order has none


def test_returned_data_matches_the_db(client: TestClient) -> None:
    """The P5-DB-4 confirm: endpoint output reconciles with the tables."""
    engine = client.app.dependency_overrides[get_readback_engine]()
    risk_repo = RiskCheckRepository(engine)
    order_repo = OrderRepository(engine)

    all_checks = client.get("/risk/checks").json()
    all_orders = client.get("/orders").json()

    assert len(all_checks) == risk_repo.count() == 2
    assert len(all_orders) == order_repo.count() == 2

    cycle_a_order = client.get("/orders", params={"cycle_id": "cycle_a"}).json()[0]
    assert len(cycle_a_order["fills"]) == len(
        order_repo.fills_for(cycle_a_order["id"])
    )


def test_execution_returns_filled_result_for_cycle(client: TestClient) -> None:
    response = client.get("/execution", params={"cycle_id": "cycle_a"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cycle_id"] == "cycle_a"
    assert body["status"] == "FILLED"
    assert body["broker_order_id"] == "alpaca-a-1"
    assert body["failed_legs"] == []
    assert [leg["leg_symbol"] for leg in body["filled_legs"]] == [
        "AAPL260320P00145000",
        "AAPL260320P00135000",
    ]
    # actual_cost is the unsigned notional: (1 * 3.15 + 1 * 1.05) * 100
    assert body["actual_cost"] == 420.0
    assert body["slippage"] == pytest.approx(0.005)


def test_execution_returns_failed_result_for_rejected_order(client: TestClient) -> None:
    response = client.get("/execution", params={"cycle_id": "cycle_b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["filled_legs"] == []
    assert body["error"]


def test_execution_without_cycle_returns_most_recent_order(client: TestClient) -> None:
    # cycle_b's order was inserted after cycle_a's, so it's "latest" overall.
    response = client.get("/execution")

    assert response.status_code == 200, response.text
    assert response.json()["cycle_id"] == "cycle_b"


def test_execution_404s_when_cycle_has_no_order(client: TestClient) -> None:
    response = client.get("/execution", params={"cycle_id": "cycle_never_executed"})

    assert response.status_code == 404


def test_execution_filled_order_tolerates_occ_symbol_casing_mismatch(
    client: TestClient,
) -> None:
    """A FILLED order never reports failed_legs even if occ_symbol casing/
    whitespace on the persisted plan leg doesn't line up with the fill's
    leg_symbol — orders.status is authoritative, not the symbol diff."""
    engine = client.app.dependency_overrides[get_readback_engine]()
    OrderRepository(engine).save_with_fills(
        OrderRecord(
            cycle_id="cycle_casing",
            order_class="SINGLE",
            status="FILLED",
            legs=[{"occ_symbol": " aapl260320p00145000 ", "side": "BUY"}],
            broker_order_id="alpaca-casing-1",
        ),
        [FillRecord(order_id=0, leg_symbol="AAPL260320P00145000", qty=Decimal("1"), price=Decimal("3.15"))],
    )

    response = client.get("/execution", params={"cycle_id": "cycle_casing"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "FILLED"
    assert response.json()["failed_legs"] == []


def test_execution_drops_a_fractional_fill_qty_without_crashing(client: TestClient) -> None:
    """A malformed persisted qty < 1 can't become a FilledLeg (qty > 0); the
    endpoint drops it rather than raising a 500 out of pydantic validation."""
    engine = client.app.dependency_overrides[get_readback_engine]()
    OrderRepository(engine).save_with_fills(
        OrderRecord(
            cycle_id="cycle_fractional",
            order_class="SINGLE",
            status="FILLED",
            broker_order_id="alpaca-fractional-1",
        ),
        [FillRecord(order_id=0, leg_symbol="X", qty=Decimal("0.4"), price=Decimal("4.0"))],
    )

    response = client.get("/execution", params={"cycle_id": "cycle_fractional"})

    assert response.status_code == 200, response.text
    assert response.json()["filled_legs"] == []


def test_execution_partially_filled_reports_the_unfilled_leg(client: TestClient) -> None:
    engine = client.app.dependency_overrides[get_readback_engine]()
    OrderRepository(engine).save_with_fills(
        OrderRecord(
            cycle_id="cycle_partial",
            order_class="MLEG",
            status="PARTIALLY_FILLED",
            legs=[
                {"occ_symbol": "AAPL260320P00145000", "side": "BUY"},
                {"occ_symbol": "AAPL260320P00135000", "side": "SELL"},
            ],
            broker_order_id="alpaca-partial-1",
        ),
        [FillRecord(order_id=0, leg_symbol="AAPL260320P00145000", qty=Decimal("1"), price=Decimal("3.15"))],
    )

    response = client.get("/execution", params={"cycle_id": "cycle_partial"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PARTIALLY_FILLED"
    assert [leg["leg_symbol"] for leg in body["failed_legs"]] == ["AAPL260320P00135000"]


def test_execution_expired_order_maps_to_cancelled_not_a_fabricated_failure(
    client: TestClient,
) -> None:
    engine = client.app.dependency_overrides[get_readback_engine]()
    OrderRepository(engine).create(
        OrderRecord(cycle_id="cycle_expired", order_class="SINGLE", status="EXPIRED")
    )

    response = client.get("/execution", params={"cycle_id": "cycle_expired"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


def test_execution_404s_on_a_non_terminal_order_instead_of_faking_a_result(
    client: TestClient,
) -> None:
    engine = client.app.dependency_overrides[get_readback_engine]()
    OrderRepository(engine).create(
        OrderRecord(cycle_id="cycle_in_flight", order_class="SINGLE", status="SUBMITTED")
    )

    response = client.get("/execution", params={"cycle_id": "cycle_in_flight"})

    assert response.status_code == 404


def test_empty_db_returns_empty_lists(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'empty_exec_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            assert test_client.get("/risk/checks").json() == []
            assert test_client.get("/orders").json() == []
            assert test_client.get("/execution").status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
