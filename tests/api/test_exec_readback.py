"""Execution read-back endpoint tests — task P5-DB-4.

* ``GET /risk/checks?cycle_id=`` filters by ``cycle_id``; without it, every row.
* ``GET /orders?cycle_id=`` filters by ``cycle_id`` and each order **includes
  its fills nested**; without it, every order.
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
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
