"""Tests for the market-data client — task P3-BE-1.

No network: an ``httpx.MockTransport`` captures each outgoing request and feeds
back a recorded Alpaca market-data payload. Covers typed-bar parsing, the
empty-feed case, pagination, multi-symbol grouping, spot prices, index proxies,
and the "upstream 5xx -> typed error, no crash" contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from backend.config import Settings
from backend.integrations.market_data import (
    Bar,
    MarketDataClient,
    MarketDataError,
    Trade,
    parse_bar,
    resolve_index_symbol,
)

_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/db",
    "ALPACA_API_KEY": "PKTEST1234567890",
    "ALPACA_SECRET_KEY": "secret-abcdefghijklmnop",
    "ALPACA_DATA_URL": "https://data.alpaca.markets/v2",
    "ALPACA_PAPER": "true",
}

# A recorded SPY daily-bars response, trimmed to three sessions.
_BARS_RESPONSE = {
    "bars": [
        {"t": "2024-01-02T05:00:00Z", "o": 472.16, "h": 473.67, "l": 470.49,
         "c": 472.65, "v": 78448200, "n": 683244, "vw": 472.03},
        {"t": "2024-01-03T05:00:00Z", "o": 470.43, "h": 471.19, "l": 468.17,
         "c": 468.79, "v": 82525500, "n": 712308, "vw": 469.33},
        {"t": "2024-01-04T05:00:00Z", "o": 468.30, "h": 470.96, "l": 467.05,
         "c": 467.28, "v": 74211800, "n": 651421, "vw": 468.79},
    ],
    "symbol": "SPY",
    "next_page_token": None,
}


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key, value in {**_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def _transport(
    sink: list[httpx.Request],
    *,
    status: int = 200,
    json: object = None,
    handler: object = None,
) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        if handler is not None:
            return handler(request)  # type: ignore[operator]
        return httpx.Response(status, json=json if json is not None else {})

    return httpx.MockTransport(_handler)


def _client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> MarketDataClient:
    return MarketDataClient(_settings(monkeypatch), transport=transport)


def test_get_bars_parses_recorded_response_into_typed_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recorded bars payload becomes a list of typed :class:`Bar`."""
    with _client(monkeypatch, _transport([], json=_BARS_RESPONSE)) as client:
        bars = client.get_bars("SPY", timeframe="1Day", start="2024-01-01")

    assert len(bars) == 3
    assert all(isinstance(b, Bar) for b in bars)
    first = bars[0]
    assert first.symbol == "SPY"
    assert first.open == 472.16
    assert first.close == 472.65
    assert first.volume == 78448200.0
    assert first.trade_count == 683244
    assert first.vwap == 472.03
    assert first.timestamp == datetime(2024, 1, 2, 5, 0, tzinfo=timezone.utc)


def test_get_bars_sends_expected_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """timeframe / start / end land on the request URL; path is symbol-scoped."""
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_BARS_RESPONSE)) as client:
        client.get_bars(
            "spy",
            timeframe="1Day",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )

    assert len(requests) == 1
    sent = requests[0]
    assert sent.url.path == "/v2/stocks/SPY/bars"
    assert sent.url.params["timeframe"] == "1Day"
    assert sent.url.params["start"] == "2024-01-01T00:00:00Z"
    assert sent.url.params["end"] == "2024-01-31T00:00:00Z"
    assert sent.headers["APCA-API-KEY-ID"] == "PKTEST1234567890"
    assert sent.headers["APCA-API-SECRET-KEY"] == "secret-abcdefghijklmnop"


@pytest.mark.parametrize("payload", [{"bars": [], "next_page_token": None}, {"bars": None}])
def test_get_bars_empty_feed_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    """No bars in the response yields an empty list, not an error."""
    with _client(monkeypatch, _transport([], json=payload)) as client:
        assert client.get_bars("SPY") == []


def test_upstream_5xx_raises_typed_error_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upstream 503 surfaces as :class:`MarketDataError`."""
    with _client(
        monkeypatch, _transport([], status=503, json={"message": "unavailable"})
    ) as client:
        with pytest.raises(MarketDataError):
            client.get_bars("SPY")


def test_2xx_non_json_body_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 with an HTML/edge-proxy body surfaces as :class:`MarketDataError`."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with _client(monkeypatch, _transport([], handler=handler)) as client:
        with pytest.raises(MarketDataError):
            client.get_bars("SPY")


def test_get_bars_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    """``next_page_token`` is walked until exhausted and bars are concatenated."""
    pages = {
        None: {
            "bars": [_BARS_RESPONSE["bars"][0]],
            "next_page_token": "PAGE-2",
        },
        "PAGE-2": {
            "bars": [_BARS_RESPONSE["bars"][1], _BARS_RESPONSE["bars"][2]],
            "next_page_token": None,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("page_token")
        return httpx.Response(200, json=pages[token])

    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, handler=handler)) as client:
        bars = client.get_bars("SPY")

    assert len(requests) == 2
    assert [b.close for b in bars] == [472.65, 468.79, 467.28]


def test_get_bars_multi_groups_by_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    """The multi-symbol endpoint returns ``{symbol: [Bar, ...]}``."""
    payload = {
        "bars": {
            "SPY": [_BARS_RESPONSE["bars"][0]],
            "AAPL": [{"t": "2024-01-02T05:00:00Z", "o": 187.15, "h": 188.44,
                      "l": 183.89, "c": 185.64, "v": 82488700, "n": 700000, "vw": 185.9}],
        },
        "next_page_token": None,
    }
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=payload)) as client:
        by_symbol = client.get_bars_multi(["spy", "aapl"], timeframe="1Day")

    assert requests[0].url.params["symbols"] == "SPY,AAPL"
    assert set(by_symbol) == {"SPY", "AAPL"}
    assert by_symbol["AAPL"][0].close == 185.64


def test_get_latest_trade_and_spot_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_latest_trade`` parses the print; ``get_spot_price`` unwraps its price."""
    payload = {
        "symbol": "SPY",
        "trade": {"t": "2024-06-03T19:59:59.936Z", "x": "V", "p": 527.8, "s": 100,
                  "c": ["@"], "i": 1, "z": "B"},
    }
    with _client(monkeypatch, _transport([], json=payload)) as client:
        trade = client.get_latest_trade("SPY")
        assert isinstance(trade, Trade)
        assert trade.price == 527.8
        assert trade.size == 100.0
        assert trade.timestamp.tzinfo is not None

    with _client(monkeypatch, _transport([], json=payload)) as client:
        assert client.get_spot_price("SPY") == 527.8


def test_missing_trade_in_response_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(monkeypatch, _transport([], json={"symbol": "SPY"})) as client:
        with pytest.raises(MarketDataError):
            client.get_latest_trade("SPY")


def test_non_object_payload_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2xx body that decodes to a JSON array (not an object) is a typed error."""
    with _client(monkeypatch, _transport([], json=["unexpected"])) as client:
        with pytest.raises(MarketDataError):
            client.get_bars("SPY")


def test_malformed_bar_raises_typed_error() -> None:
    """A bar missing the close price is a typed error, not a KeyError."""
    with pytest.raises(MarketDataError):
        parse_bar("SPY", {"t": "2024-01-02T05:00:00Z", "o": 1, "h": 2, "l": 0})


def test_resolve_index_symbol_maps_headline_indices() -> None:
    assert resolve_index_symbol("sp500") == "SPY"
    assert resolve_index_symbol("SPX") == "SPY"
    assert resolve_index_symbol("nasdaq 100") == "QQQ"
    assert resolve_index_symbol("VIX") == "VIXY"
    with pytest.raises(MarketDataError):
        resolve_index_symbol("ftse100")


def test_get_index_bars_uses_proxy_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_BARS_RESPONSE)) as client:
        bars = client.get_index_bars("sp500", timeframe="1Day")

    assert requests[0].url.path == "/v2/stocks/SPY/bars"
    assert len(bars) == 3
