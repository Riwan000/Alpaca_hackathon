"""Market-data client — task P3-BE-1.

A thin synchronous wrapper over the Alpaca **market-data** REST API
(``data.alpaca.markets``): historical OHLCV bars, latest-trade spot prices, and
index data (via the liquid ETF proxy for each headline index).

Credentials and the data host come from :class:`backend.config.Settings`; the
key/secret auth is identical to the trading client, so this module reuses
:func:`backend.integrations.alpaca.client.resolve_alpaca_config` and
:func:`~backend.integrations.alpaca.client.build_auth_headers`.

The HTTP layer is plain :mod:`httpx`, so tests inject an ``httpx.MockTransport``
and feed canned JSON without a network call. Every upstream failure surfaces as
:class:`MarketDataError` — an upstream 5xx never crashes the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

from backend.config import Settings, get_settings
from backend.integrations._http import (
    expect_object,
    format_query_date,
    join_symbols,
    parse_timestamp,
    request_json,
)
from backend.integrations.alpaca.client import build_auth_headers, resolve_alpaca_config

_BARS_PATH = "/stocks/{symbol}/bars"
_BARS_MULTI_PATH = "/stocks/bars"
_LATEST_TRADE_PATH = "/stocks/{symbol}/trades/latest"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_TIMEFRAME = "1Day"
_DEFAULT_ADJUSTMENT = "raw"
# Alpaca caps a bars page at 10 000 rows and we cap the page walk so a bad
# ``next_page_token`` loop can never run unbounded.
_MAX_PAGE_LIMIT = 10_000
_MAX_PAGES = 50

# Headline index -> the most liquid tradable proxy Alpaca serves bars for.
INDEX_PROXY_SYMBOLS: dict[str, str] = {
    "sp500": "SPY",
    "nasdaq100": "QQQ",
    "dow": "DIA",
    "russell2000": "IWM",
    "vix": "VIXY",
}

_INDEX_ALIASES: dict[str, str] = {
    "spx": "sp500",
    "spy": "sp500",
    "s&p500": "sp500",
    "sandp500": "sp500",
    "ndx": "nasdaq100",
    "nasdaq": "nasdaq100",
    "qqq": "nasdaq100",
    "djia": "dow",
    "dji": "dow",
    "dowjones": "dow",
    "dia": "dow",
    "rut": "russell2000",
    "russell": "russell2000",
    "iwm": "russell2000",
    "vixy": "vix",
    "volatility": "vix",
}


class MarketDataError(RuntimeError):
    """Raised when the market-data API errors, is unreachable, or returns junk."""


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar for ``symbol`` over a single timeframe bucket."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None
    vwap: float | None = None


@dataclass(frozen=True)
class Trade:
    """The most recent print for ``symbol`` — used as the spot price."""

    symbol: str
    timestamp: datetime
    price: float
    size: float


def parse_bar(symbol: str, raw: Mapping[str, Any]) -> Bar:
    """Parse one Alpaca bar object (``{"t","o","h","l","c","v","n","vw"}``)."""
    try:
        return Bar(
            symbol=symbol,
            timestamp=parse_timestamp(str(raw["t"])),
            open=float(raw["o"]),
            high=float(raw["h"]),
            low=float(raw["l"]),
            close=float(raw["c"]),
            volume=float(raw["v"]),
            trade_count=int(raw["n"]) if raw.get("n") is not None else None,
            vwap=float(raw["vw"]) if raw.get("vw") is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketDataError(f"malformed bar for {symbol}: {raw!r}") from exc


def _parse_trade(symbol: str, raw: Mapping[str, Any]) -> Trade:
    try:
        return Trade(
            symbol=symbol,
            timestamp=parse_timestamp(str(raw["t"])),
            price=float(raw["p"]),
            size=float(raw["s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketDataError(f"malformed trade for {symbol}: {raw!r}") from exc


def resolve_index_symbol(name: str) -> str:
    """Map a headline index name (``"sp500"``, ``"vix"``, ``"SPX"``, ...) to its proxy."""
    key = "".join(ch for ch in name.strip().lower() if not ch.isspace())
    key = key.replace("-", "").replace("_", "")
    canonical = _INDEX_ALIASES.get(key, key)
    try:
        return INDEX_PROXY_SYMBOLS[canonical]
    except KeyError as exc:
        known = ", ".join(sorted(INDEX_PROXY_SYMBOLS))
        raise MarketDataError(
            f"unknown index {name!r}; known indices: {known}"
        ) from exc


class MarketDataClient:
    """Synchronous client for the Alpaca market-data REST API.

    Construct it with the process :class:`Settings` (the default). Pass
    ``transport`` to redirect HTTP at a mock in tests. Usable as a context
    manager so the underlying connection pool is closed.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        cfg = settings or get_settings()
        self._config = resolve_alpaca_config(cfg)
        client_kwargs: dict[str, Any] = {
            "base_url": cfg.alpaca_data_url.rstrip("/"),
            "headers": build_auth_headers(self._config),
            "timeout": timeout,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.Client(**client_kwargs)

    @property
    def base_url(self) -> str:
        """The market-data host every request is sent to."""
        return str(self._client.base_url)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Mapping[str, Any]:
        data = request_json(
            self._client, path, params=params, error_cls=MarketDataError, label="market-data"
        )
        return expect_object(data, error_cls=MarketDataError, label="market-data")

    def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str = _DEFAULT_TIMEFRAME,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        limit: int | None = None,
        adjustment: str = _DEFAULT_ADJUSTMENT,
        feed: str | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> list[Bar]:
        """Return historical bars for ``symbol``, following pagination to the end."""
        params: dict[str, Any] = {"timeframe": timeframe, "adjustment": adjustment}
        if start is not None:
            params["start"] = format_query_date(start)
        if end is not None:
            params["end"] = format_query_date(end)
        if limit is not None:
            params["limit"] = min(int(limit), _MAX_PAGE_LIMIT)
        if feed is not None:
            params["feed"] = feed

        path = _BARS_PATH.format(symbol=symbol.strip().upper())
        out: list[Bar] = []
        token: str | None = None
        for _ in range(max(1, max_pages)):
            page_params = dict(params)
            if token:
                page_params["page_token"] = token
            data = self._get(path, page_params)
            for raw in data.get("bars") or []:
                out.append(parse_bar(symbol.strip().upper(), raw))
            token = data.get("next_page_token")
            if not token:
                break
        return out

    def get_bars_multi(
        self,
        symbols: str | Iterable[str],
        *,
        timeframe: str = _DEFAULT_TIMEFRAME,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        limit: int | None = None,
        adjustment: str = _DEFAULT_ADJUSTMENT,
        feed: str | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> dict[str, list[Bar]]:
        """Return ``{symbol: [Bar, ...]}`` for several symbols in one call."""
        params: dict[str, Any] = {
            "symbols": join_symbols(symbols),
            "timeframe": timeframe,
            "adjustment": adjustment,
        }
        if start is not None:
            params["start"] = format_query_date(start)
        if end is not None:
            params["end"] = format_query_date(end)
        if limit is not None:
            params["limit"] = min(int(limit), _MAX_PAGE_LIMIT)
        if feed is not None:
            params["feed"] = feed

        result: dict[str, list[Bar]] = {}
        token: str | None = None
        for _ in range(max(1, max_pages)):
            page_params = dict(params)
            if token:
                page_params["page_token"] = token
            data = self._get(_BARS_MULTI_PATH, page_params)
            bars_by_symbol = data.get("bars") or {}
            if not isinstance(bars_by_symbol, Mapping):
                raise MarketDataError(
                    f"expected a bars object keyed by symbol, got {type(bars_by_symbol).__name__}"
                )
            for sym, raw_list in bars_by_symbol.items():
                bucket = result.setdefault(sym, [])
                for raw in raw_list or []:
                    bucket.append(parse_bar(sym, raw))
            token = data.get("next_page_token")
            if not token:
                break
        return result

    def get_latest_trade(self, symbol: str) -> Trade:
        """Return the most recent print for ``symbol``."""
        sym = symbol.strip().upper()
        data = self._get(_LATEST_TRADE_PATH.format(symbol=sym))
        raw = data.get("trade")
        if not raw:
            raise MarketDataError(f"no latest trade in response for {sym}: {data!r}")
        return _parse_trade(sym, raw)

    def get_spot_price(self, symbol: str) -> float:
        """Return the latest trade price for ``symbol`` as a float."""
        return self.get_latest_trade(symbol).price

    def get_index_bars(
        self,
        index: str,
        *,
        timeframe: str = _DEFAULT_TIMEFRAME,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        limit: int | None = None,
        adjustment: str = _DEFAULT_ADJUSTMENT,
        feed: str | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> list[Bar]:
        """Return bars for a headline index via its ETF proxy (see :data:`INDEX_PROXY_SYMBOLS`)."""
        return self.get_bars(
            resolve_index_symbol(index),
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
            adjustment=adjustment,
            feed=feed,
            max_pages=max_pages,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> MarketDataClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
