"""Alpaca account read-back and synchronization endpoints.

Provides:
- ``GET /alpaca/account``: fetches the live Alpaca trading account and open positions,
  matching the provided account ID / account number.
- ``POST /portfolio/sync-alpaca``: syncs the live Alpaca balance and positions into
  the ``portfolio_snapshots`` database table.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from backend.api.readback import PositionOut, get_readback_engine
from backend.config import Settings, get_settings
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)
from backend.integrations.alpaca import AlpacaClient, resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError, AlpacaError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alpaca"])


class AlpacaAccountOut(BaseModel):
    account_id: str
    account_number: str
    status: str
    currency: str
    portfolio_value: float
    cash: float
    equity: float
    buying_power: float
    long_market_value: float
    short_market_value: float
    last_equity: float | None = None
    positions: list[PositionOut]


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _dec(val: Any) -> decimal.Decimal:
    return decimal.Decimal(str(_f(val)))


def get_alpaca_client(settings: Settings = Depends(get_settings)) -> AlpacaClient:
    """FastAPI dependency for resolving an authenticated AlpacaClient."""
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError as exc:
        raise HTTPException(
            status_code=503,
            detail="Alpaca credentials not configured in environment.",
        ) from exc
    return AlpacaClient(settings)


@router.get("/alpaca/account", response_model=AlpacaAccountOut)
def get_alpaca_account(
    account_id: str | None = Query(
        default=None,
        description="Alpaca account ID (UUID) or account number (e.g. PA3...)",
    ),
    client: AlpacaClient = Depends(get_alpaca_client),
) -> AlpacaAccountOut:
    """Fetch live Alpaca dashboard account balance and active holdings."""
    try:
        with client:
            account = client.get_account()
            raw_positions = client.get_positions()
    except HTTPException:
        raise
    except AlpacaError as exc:
        logger.error("Alpaca API error fetching account: %s", exc)
        raise HTTPException(status_code=502, detail=f"Alpaca API error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error querying Alpaca account")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    acc_id = str(account.get("id", ""))
    acc_num = str(account.get("account_number", ""))

    # If an ID is provided, verify it matches either the UUID id or account_number
    if account_id:
        target = account_id.strip().lower()
        if target != acc_id.lower() and target != acc_num.lower():
            raise HTTPException(
                status_code=404,
                detail=f"Alpaca account '{account_id}' not found for active credentials (active: {acc_num} / {acc_id}).",
            )

    portfolio_val = _f(account.get("portfolio_value") or account.get("equity"))
    cash_val = _f(account.get("cash"))
    equity_val = _f(account.get("equity") or portfolio_val)
    buying_power_val = _f(account.get("buying_power"))
    long_market_val = _f(account.get("long_market_value"))
    short_market_val = _f(account.get("short_market_value"))
    last_equity_raw = account.get("last_equity")
    last_equity = _f(last_equity_raw) if last_equity_raw is not None else None

    positions = [
        PositionOut(
            symbol=str(p.get("symbol", "")).upper(),
            qty=_f(p.get("qty")),
            avg_price=abs(_f(p.get("avg_entry_price"))),
            market_value=_f(p.get("market_value")),
            asset_class=str(p.get("asset_class", "us_equity")),
            side=str(p.get("side", "long")),
        )
        for p in (raw_positions or [])
    ]

    return AlpacaAccountOut(
        account_id=acc_id,
        account_number=acc_num,
        status=str(account.get("status", "ACTIVE")),
        currency=str(account.get("currency", "USD")),
        portfolio_value=portfolio_val,
        cash=cash_val,
        equity=equity_val,
        buying_power=buying_power_val,
        long_market_value=long_market_val,
        short_market_value=short_market_val,
        last_equity=last_equity,
        positions=positions,
    )


class SyncAlpacaOut(BaseModel):
    snapshot_id: int
    cycle_id: str
    total_value: float
    cash: float
    equity: float
    buying_power: float
    positions_count: int


@router.post("/portfolio/sync-alpaca", response_model=SyncAlpacaOut)
def sync_alpaca_to_portfolio(
    engine: Engine = Depends(get_readback_engine),
    client: AlpacaClient = Depends(get_alpaca_client),
) -> SyncAlpacaOut:
    """Read live Alpaca account state and record a snapshot into the database."""
    try:
        with client:
            account = client.get_account()
            raw_positions = client.get_positions()
    except HTTPException:
        raise
    except AlpacaError as exc:
        raise HTTPException(status_code=502, detail=f"Alpaca API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    now = _dt.datetime.now(_dt.timezone.utc)
    cycle_id = f"alpaca_{now.strftime('%Y%m%d_%H%M%S')}"

    portfolio_val = _f(account.get("portfolio_value") or account.get("equity"))
    cash_val = _f(account.get("cash"))
    equity_val = _f(account.get("equity") or portfolio_val)
    buying_power_val = _f(account.get("buying_power"))

    snapshot = PortfolioSnapshotRecord(
        cycle_id=cycle_id,
        total_value=_dec(portfolio_val),
        cash=_dec(cash_val),
        equity=_dec(equity_val),
        buying_power=_dec(buying_power_val),
        ts=now,
    )

    positions = [
        PositionRecord(
            symbol=str(p.get("symbol", "")).upper(),
            qty=_dec(p.get("qty")),
            avg_price=_dec(abs(_f(p.get("avg_entry_price")))),
            market_value=_dec(p.get("market_value")),
            asset_class=str(p.get("asset_class", "us_equity")),
            side=str(p.get("side", "long")),
        )
        for p in (raw_positions or [])
    ]

    repo = PortfolioSnapshotRepository(engine)
    saved = repo.save_with_positions(snapshot, positions)

    return SyncAlpacaOut(
        snapshot_id=saved.snapshot.id or 0,
        cycle_id=cycle_id,
        total_value=portfolio_val,
        cash=cash_val,
        equity=equity_val,
        buying_power=buying_power_val,
        positions_count=len(positions),
    )
