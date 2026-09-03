"""Live analysis-inputs builder — task P3-BE-12 (BRD §11–14).

``POST /analyze`` needs one :class:`~backend.agents.context_builder.AnalysisInputs`
bundle per cycle, assembled from the integration layer:

* **portfolio** (required) — the Alpaca paper account + open positions
  (:mod:`backend.integrations.alpaca`);
* **market data** (best effort) — SPY trend / last price + a daily bar per held
  name (:mod:`backend.integrations.market_data`);
* **news** (best effort) — the Alpaca news feed for the held symbols
  (:mod:`backend.integrations.news`);
* **option chains** (best effort) — a near-dated put chain for the hedge
  underlyings (:mod:`backend.integrations.alpaca` options snapshot).

Only the portfolio fetch is fatal: if Alpaca cannot return the account or the
positions, :class:`IngestError` is raised and the endpoint answers ``503``.
Every other source is wrapped so an upstream failure yields an *empty* slice
(``[]`` / a bare :class:`MarketData`) rather than aborting the cycle — the
analysis pass then degrades that section (BRD §31), it does not crash.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.agents.context_builder import (
    AnalysisInputs,
    MarketData,
    OptionChain,
    OptionQuoteRow,
    RawNewsArticle,
    SymbolBar,
)
from backend.config import Settings, get_settings
from backend.integrations.alpaca import AlpacaClient, OptionChainClient
from backend.integrations.market_data import MarketDataClient
from backend.integrations.news import NewsClient
from backend.models.common import PortfolioPosition
from backend.models.enums import AssetClass, OptionRight, OrderSide
from backend.models.hedge_context import HedgeObjective, PortfolioState

logger = logging.getLogger(__name__)

__all__ = ["IngestError", "build_live_analysis_inputs"]

_INDEX_LOOKBACK_DAYS = 30
_BAR_LOOKBACK_DAYS = 10
_NEWS_LIMIT = 20
_OPTION_MIN_DTE = 7
_OPTION_MAX_DTE = 60
_MAX_OPTION_UNDERLYINGS = 2

_ASSET_CLASS_MAP = {
    "us_equity": AssetClass.EQUITY,
    "equity": AssetClass.EQUITY,
    "us_option": AssetClass.OPTION,
    "option": AssetClass.OPTION,
    "crypto": AssetClass.EQUITY,  # no dedicated enum member in the MVP
}


class IngestError(RuntimeError):
    """The portfolio could not be read from Alpaca — the cycle cannot start."""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _position(raw: dict[str, Any]) -> PortfolioPosition:
    side = OrderSide.SELL if str(raw.get("side", "long")).lower() == "short" else OrderSide.BUY
    asset_class = _ASSET_CLASS_MAP.get(str(raw.get("asset_class", "")).lower(), AssetClass.EQUITY)
    upl = raw.get("unrealized_pl")
    return PortfolioPosition(
        symbol=str(raw["symbol"]).upper(),
        qty=_f(raw.get("qty")),
        avg_price=abs(_f(raw.get("avg_entry_price"))),
        market_value=_f(raw.get("market_value")),
        asset_class=asset_class,
        side=side,
        unrealized_pl=None if upl is None else _f(upl),
    )


def _portfolio_state(settings: Settings) -> PortfolioState:
    try:
        with AlpacaClient(settings) as client:
            account = client.get_account()
            raw_positions = client.get_positions()
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean 503 by the endpoint
        raise IngestError(f"could not read the Alpaca portfolio: {exc}") from exc

    total_value = _f(account.get("portfolio_value") or account.get("equity"))
    return PortfolioState(
        total_value=total_value,
        cash=_f(account.get("cash")),
        equity=_f(account.get("equity") or account.get("portfolio_value")),
        buying_power=_f(account.get("buying_power")),
        positions=[_position(p) for p in raw_positions],
    )


def _trend(first: float, last: float) -> str:
    if last > first:
        return "UP"
    if last < first:
        return "DOWN"
    return "FLAT"


def _market_data(settings: Settings, symbols: list[str], now: datetime) -> MarketData:
    """SPY trend + last price and one recent daily bar per held name (best effort)."""
    try:
        with MarketDataClient(settings) as md:
            index_trend: str | None = None
            index_price: float | None = None
            try:
                index_bars = md.get_index_bars(
                    "sp500", start=now - timedelta(days=_INDEX_LOOKBACK_DAYS)
                )
                if index_bars:
                    index_trend = _trend(index_bars[0].close, index_bars[-1].close)
                    index_price = index_bars[-1].close
            except Exception:  # noqa: BLE001 - index data is optional
                logger.warning("index data unavailable for this cycle", exc_info=True)

            per_symbol: list[SymbolBar] = []
            if symbols:
                try:
                    by_symbol = md.get_bars_multi(
                        symbols,
                        start=now - timedelta(days=_BAR_LOOKBACK_DAYS),
                    )
                    for sym in symbols:
                        bars = by_symbol.get(sym) or by_symbol.get(sym.upper()) or []
                        if not bars:
                            continue
                        last = bars[-1].close
                        prior = bars[-2].close if len(bars) >= 2 else None
                        per_symbol.append(
                            SymbolBar(
                                symbol=sym.upper(),
                                last_price=last,
                                prior_close=prior if prior and prior > 0 else None,
                            )
                        )
                except Exception:  # noqa: BLE001 - per-holding bars are optional
                    logger.warning("per-symbol bars unavailable for this cycle", exc_info=True)

        return MarketData(
            index_symbol="SPY",
            index_trend=index_trend,
            index_price=index_price if index_price and index_price > 0 else None,
            per_symbol=per_symbol,
            as_of=now,
        )
    except Exception:  # noqa: BLE001 - the whole market slice is best effort
        logger.warning("market-data client unavailable; market slice empty", exc_info=True)
        return MarketData(index_symbol="SPY", as_of=now)


def _news_feed(settings: Settings, symbols: list[str]) -> list[RawNewsArticle]:
    if not symbols:
        return []
    try:
        with NewsClient(settings) as news:
            articles = news.get_news(symbols, limit=_NEWS_LIMIT, include_content=True)
    except Exception:  # noqa: BLE001 - the news slice is best effort
        logger.warning("news feed unavailable; news slice empty", exc_info=True)
        return []
    return [
        RawNewsArticle(
            headline=a.headline,
            ts=a.ts,
            body=a.summary,
            symbols=list(a.symbols),
            source=a.source,
        )
        for a in articles
    ]


def _option_chains(settings: Settings, underlyings: list[str], now: datetime) -> list[OptionChain]:
    if not underlyings:
        return []
    lo = (now + timedelta(days=_OPTION_MIN_DTE)).date()
    hi = (now + timedelta(days=_OPTION_MAX_DTE)).date()
    chains: list[OptionChain] = []
    try:
        with OptionChainClient(settings) as oc:
            for sym in underlyings[:_MAX_OPTION_UNDERLYINGS]:
                try:
                    contracts = oc.get_chain(
                        sym, expiration_gte=lo, expiration_lte=hi, right="put", max_pages=1
                    )
                except Exception:  # noqa: BLE001 - one underlying failing is fine
                    logger.warning("option chain unavailable for %s", sym, exc_info=True)
                    continue
                quotes = [
                    OptionQuoteRow(
                        right=OptionRight.PUT,
                        strike=c.strike,
                        expiration=c.expiry,
                        bid=c.bid if c.bid and c.bid > 0 else None,
                        ask=c.ask if c.ask and c.ask > 0 else None,
                        last=c.last_price if c.last_price and c.last_price > 0 else None,
                        iv=c.implied_vol if c.implied_vol and c.implied_vol >= 0 else None,
                        delta=c.greeks.delta,
                    )
                    for c in contracts
                ]
                if quotes:
                    chains.append(OptionChain(underlying=sym.upper(), quotes=quotes))
    except Exception:  # noqa: BLE001 - the whole options slice is best effort
        logger.warning("option-chain client unavailable; options slice empty", exc_info=True)
        return []
    return chains


def build_live_analysis_inputs(
    *,
    settings: Settings | None = None,
    cycle_id: str | None = None,
    now: datetime | None = None,
) -> AnalysisInputs:
    """Assemble one cycle's :class:`AnalysisInputs` from the live integrations."""
    cfg = settings or get_settings()
    ts = now or datetime.now(timezone.utc)
    cid = cycle_id or f"cyc-{uuid.uuid4().hex[:12]}"

    portfolio = _portfolio_state(cfg)
    held = sorted({p.symbol for p in portfolio.positions})

    return AnalysisInputs(
        cycle_id=cid,
        timestamp=ts,
        objective=HedgeObjective(
            max_hedge_budget_pct=cfg.max_hedge_budget_pct,
            drawdown_tolerance_pct=cfg.drawdown_trigger_pct,
        ),
        portfolio_state=portfolio,
        market_data=_market_data(cfg, held, ts),
        news_feed=_news_feed(cfg, held),
        option_chains=_option_chains(cfg, held, ts),
        hedge_underlyings=held,
    )
