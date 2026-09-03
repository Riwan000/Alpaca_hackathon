"""Read-back endpoint tests — task P3-DB-4.

* ``GET /portfolio/latest`` returns the newest ``portfolio_snapshots`` row, its
  risk metrics, and its positions.
* ``GET /agent-runs`` filters by ``cycle_id`` and orders by ``started_at``;
  without ``cycle_id`` it returns every run, still in ``started_at`` order.
"""

from __future__ import annotations

import datetime
import decimal
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.agent_runs_repo import AgentRunRecord, AgentRunRepository
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration

_UTC = datetime.timezone.utc


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot(cycle_id: str, ts: datetime.datetime, **metrics: decimal.Decimal) -> PortfolioSnapshotRecord:
    return PortfolioSnapshotRecord(
        cycle_id=cycle_id,
        total_value=decimal.Decimal("100000.0000"),
        cash=decimal.Decimal("25000.0000"),
        equity=decimal.Decimal("75000.0000"),
        buying_power=decimal.Decimal("50000.0000"),
        ts=ts,
        **metrics,
    )


def _position(symbol: str) -> PositionRecord:
    return PositionRecord(
        symbol=symbol,
        qty=decimal.Decimal("100.0000"),
        avg_price=decimal.Decimal("150.0000"),
        market_value=decimal.Decimal("15000.0000"),
        asset_class="us_equity",
        side="long",
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App wired to a migrated, seeded scratch DB via the read-back dependency."""
    db_url = f"sqlite:///{tmp_path / 'readback_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)

    snap_repo = PortfolioSnapshotRepository(engine)
    # Older snapshot first, then the newest — the one /portfolio/latest must return.
    snap_repo.save_with_positions(
        _snapshot("cycle_old", datetime.datetime(2026, 9, 3, 14, 0, tzinfo=_UTC)),
        [_position("OLD")],
    )
    snap_repo.save_with_positions(
        _snapshot(
            "cycle_new",
            datetime.datetime(2026, 9, 3, 15, 30, tzinfo=_UTC),
            volatility=decimal.Decimal("0.1850"),
            beta=decimal.Decimal("1.0300"),
            drawdown=decimal.Decimal("-0.0720"),
        ),
        [_position("AAPL"), _position("NVDA")],
    )

    run_repo = AgentRunRepository(engine)
    # cycle_a runs, deliberately created out of start order.
    for name, minute in [("risk_agent", 3), ("market_agent", 1), ("news_agent", 2)]:
        run_repo.create(
            AgentRunRecord(
                cycle_id="cycle_a",
                agent_name=name,
                started_at=datetime.datetime(2026, 9, 3, 15, minute, tzinfo=_UTC),
            )
        )
    run_repo.create(
        AgentRunRecord(
            cycle_id="cycle_b",
            agent_name="market_agent",
            started_at=datetime.datetime(2026, 9, 3, 15, 0, tzinfo=_UTC),
        )
    )

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_portfolio_latest_returns_the_newest_snapshot(client: TestClient) -> None:
    response = client.get("/portfolio/latest")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cycle_id"] == "cycle_new"
    assert body["total_value"] == 100000.0
    assert body["volatility"] == 0.185
    assert body["beta"] == 1.03
    assert body["drawdown"] == -0.072
    assert [p["symbol"] for p in body["positions"]] == ["AAPL", "NVDA"]


def test_agent_runs_filters_by_cycle_and_orders_by_started_at(client: TestClient) -> None:
    response = client.get("/agent-runs", params={"cycle_id": "cycle_a"})

    assert response.status_code == 200, response.text
    runs = response.json()
    assert [r["agent_name"] for r in runs] == ["market_agent", "news_agent", "risk_agent"]
    assert all(r["cycle_id"] == "cycle_a" for r in runs)
    started = [r["started_at"] for r in runs]
    assert started == sorted(started)


def test_agent_runs_without_cycle_id_returns_every_run(client: TestClient) -> None:
    runs = client.get("/agent-runs").json()

    assert len(runs) == 4
    assert {r["cycle_id"] for r in runs} == {"cycle_a", "cycle_b"}
    started = [r["started_at"] for r in runs]
    assert started == sorted(started)


def test_portfolio_latest_404_when_empty(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'empty_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)
    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/portfolio/latest")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
