"""Unit and integration tests for Alpaca API endpoints — task alpaca-dashboard-balance."""

from __future__ import annotations

import json
from typing import Any
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.alpaca import get_alpaca_client
from backend.api.readback import get_readback_engine
from backend.config import Settings
from backend.db.repository import PortfolioSnapshotRepository
from backend.integrations.alpaca.client import AlpacaClient, AlpacaConfig, PAPER_BASE_URL


MOCK_ACCOUNT = {
    "id": "b78de2d5-d310-478f-a038-66f08a62b6c1",
    "account_number": "PA3C0P4T6AJE",
    "status": "ACTIVE",
    "currency": "USD",
    "portfolio_value": "99607.64",
    "cash": "84019.09",
    "equity": "99607.64",
    "buying_power": "379724.3",
    "long_market_value": "15588.55",
    "short_market_value": "0",
    "last_equity": "99923.04",
}

MOCK_POSITIONS = [
    {
        "symbol": "AAPL",
        "qty": "10",
        "avg_entry_price": "319.79",
        "market_value": "3170.5",
        "asset_class": "us_equity",
        "side": "long",
        "unrealized_pl": "-27.4",
    },
    {
        "symbol": "MSFT",
        "qty": "5",
        "avg_entry_price": "495.0",
        "market_value": "2460.05",
        "asset_class": "us_equity",
        "side": "long",
        "unrealized_pl": "-14.95",
    },
]


def _mock_transport(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v2/account":
        return httpx.Response(200, json=MOCK_ACCOUNT)
    if path == "/v2/positions":
        return httpx.Response(200, json=MOCK_POSITIONS)
    return httpx.Response(404, json={"message": "not found"})


def _build_test_client(db_engine=None, missing_creds: bool = False) -> TestClient:
    app = create_app()

    if missing_creds:
        app.dependency_overrides[get_alpaca_client] = lambda: (_ for _ in ()).throw(
            pytest.importorskip("fastapi").HTTPException(
                status_code=503, detail="Alpaca credentials not configured"
            )
        )
    else:
        config = AlpacaConfig(
            api_key="test_key",
            secret_key="test_secret",
            base_url=PAPER_BASE_URL,
            paper=True,
        )
        transport = httpx.MockTransport(_mock_transport)
        client = AlpacaClient(config=config, transport=transport)
        app.dependency_overrides[get_alpaca_client] = lambda: client

    if db_engine is not None:
        app.dependency_overrides[get_readback_engine] = lambda: db_engine

    return TestClient(app)


def test_get_alpaca_account_success() -> None:
    client = _build_test_client()
    resp = client.get("/alpaca/account")
    assert resp.status_code == 200
    data = resp.json()

    assert data["account_id"] == "b78de2d5-d310-478f-a038-66f08a62b6c1"
    assert data["account_number"] == "PA3C0P4T6AJE"
    assert data["status"] == "ACTIVE"
    assert data["portfolio_value"] == 99607.64
    assert data["cash"] == 84019.09
    assert data["buying_power"] == 379724.3
    assert len(data["positions"]) == 2
    assert data["positions"][0]["symbol"] == "AAPL"
    assert data["positions"][0]["qty"] == 10.0


def test_get_alpaca_account_filter_by_uuid() -> None:
    client = _build_test_client()
    resp = client.get("/alpaca/account?account_id=b78de2d5-d310-478f-a038-66f08a62b6c1")
    assert resp.status_code == 200
    assert resp.json()["account_number"] == "PA3C0P4T6AJE"


def test_get_alpaca_account_filter_by_account_number() -> None:
    client = _build_test_client()
    resp = client.get("/alpaca/account?account_id=PA3C0P4T6AJE")
    assert resp.status_code == 200
    assert resp.json()["account_id"] == "b78de2d5-d310-478f-a038-66f08a62b6c1"


def test_get_alpaca_account_mismatched_id_returns_404() -> None:
    client = _build_test_client()
    resp = client.get("/alpaca/account?account_id=DIFFERENT_ACCOUNT_123")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_alpaca_account_missing_credentials_returns_503() -> None:
    client = _build_test_client(missing_creds=True)
    resp = client.get("/alpaca/account")
    assert resp.status_code == 503
    assert "credentials" in resp.json()["detail"].lower()


def test_sync_alpaca_to_portfolio(tmp_path) -> None:
    import subprocess
    import sys
    from pathlib import Path
    from backend.db import OVERRIDE_ENV_VAR, normalize_driver

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    db_url = f"sqlite:///{tmp_path / 'sync_test.db'}"

    # Migrate sqlite scratch DB
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        cwd=repo_root,
        env={**pytest.importorskip("os").environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        check=True,
    )

    engine = create_engine(normalize_driver(db_url), future=True)
    client = _build_test_client(db_engine=engine)

    resp = client.post("/portfolio/sync-alpaca")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value"] == 99607.64
    assert data["cash"] == 84019.09
    assert data["positions_count"] == 2

    repo = PortfolioSnapshotRepository(engine)
    latest = repo.latest()
    assert latest is not None
    assert float(latest.total_value) == 99607.64
    assert float(latest.cash) == 84019.09
