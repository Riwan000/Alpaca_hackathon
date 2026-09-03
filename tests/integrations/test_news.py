"""Tests for the news client — task P3-BE-2.

No network: an ``httpx.MockTransport`` feeds back a recorded Alpaca news feed.
Covers normalisation to ``{headline, ts, symbols, source}``, the empty-feed
``[]`` case, the symbols query parameter, pagination, and the
"upstream 5xx -> typed error, no crash" contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from backend.config import Settings
from backend.integrations.news import Article, NewsClient, NewsError, normalize_article

_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/db",
    "ALPACA_API_KEY": "PKTEST1234567890",
    "ALPACA_SECRET_KEY": "secret-abcdefghijklmnop",
    "ALPACA_DATA_URL": "https://data.alpaca.markets/v2",
    "ALPACA_PAPER": "true",
}

# A recorded Alpaca news feed, trimmed to two items.
_NEWS_RESPONSE = {
    "news": [
        {
            "id": 24843171,
            "headline": "Apple Reports Record Quarterly Revenue",
            "author": "Jane Doe",
            "created_at": "2024-02-01T13:30:00Z",
            "updated_at": "2024-02-01T13:35:00Z",
            "summary": "Apple posted quarterly revenue above expectations.",
            "url": "https://example.com/aapl-q1",
            "images": [],
            "symbols": ["AAPL"],
            "source": "benzinga",
        },
        {
            "id": 24843172,
            "headline": "Fed Holds Rates Steady",
            "author": "John Roe",
            "created_at": "2024-02-01T19:00:00Z",
            "updated_at": "2024-02-01T19:02:00Z",
            "summary": "The Federal Reserve left its benchmark rate unchanged.",
            "url": "https://example.com/fomc",
            "images": [],
            "symbols": ["spy", "qqq"],
            "source": "benzinga",
        },
    ],
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


def _client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> NewsClient:
    return NewsClient(_settings(monkeypatch), transport=transport)


def test_get_news_normalizes_recorded_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every raw item becomes an :class:`Article` with the four contract fields."""
    with _client(monkeypatch, _transport([], json=_NEWS_RESPONSE)) as client:
        articles = client.get_news(["AAPL", "SPY"])

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)

    first = articles[0]
    assert first.headline == "Apple Reports Record Quarterly Revenue"
    assert first.ts == datetime(2024, 2, 1, 13, 30, tzinfo=timezone.utc)
    assert first.symbols == ("AAPL",)
    assert first.source == "benzinga"
    assert first.url == "https://example.com/aapl-q1"
    assert first.id == 24843171

    # symbols are upper-cased regardless of feed casing
    assert articles[1].symbols == ("SPY", "QQQ")

    as_dict = first.as_dict()
    assert set(as_dict) >= {"headline", "ts", "symbols", "source"}
    assert as_dict["symbols"] == ["AAPL"]


@pytest.mark.parametrize("payload", [{"news": [], "next_page_token": None}, {"news": None}])
def test_get_news_empty_feed_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    """An empty feed normalises to ``[]``."""
    with _client(monkeypatch, _transport([], json=payload)) as client:
        assert client.get_news(["AAPL"]) == []


def test_get_news_sends_symbols_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Symbols are normalised onto the query; auth headers ride along; path is v1beta1."""
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_NEWS_RESPONSE)) as client:
        client.get_news(["aapl", "tsla"], limit=10)

    assert len(requests) == 1
    sent = requests[0]
    assert sent.url.path == "/v1beta1/news"
    assert sent.url.params["symbols"] == "AAPL,TSLA"
    assert sent.url.params["limit"] == "10"
    assert sent.headers["APCA-API-KEY-ID"] == "PKTEST1234567890"
    assert sent.headers["APCA-API-SECRET-KEY"] == "secret-abcdefghijklmnop"


def test_get_news_without_symbols_omits_param(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_NEWS_RESPONSE)) as client:
        client.get_news()

    assert "symbols" not in requests[0].url.params


def test_upstream_5xx_raises_typed_error_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(
        monkeypatch, _transport([], status=502, json={"message": "bad gateway"})
    ) as client:
        with pytest.raises(NewsError):
            client.get_news(["AAPL"])


def test_2xx_non_json_body_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with _client(monkeypatch, _transport([], handler=handler)) as client:
        with pytest.raises(NewsError):
            client.get_news(["AAPL"])


def test_get_news_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        None: {"news": [_NEWS_RESPONSE["news"][0]], "next_page_token": "PAGE-2"},
        "PAGE-2": {"news": [_NEWS_RESPONSE["news"][1]], "next_page_token": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("page_token")])

    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, handler=handler)) as client:
        articles = client.get_news(["AAPL", "SPY"])

    assert len(requests) == 2
    assert [a.headline for a in articles] == [
        "Apple Reports Record Quarterly Revenue",
        "Fed Holds Rates Steady",
    ]


def test_non_object_payload_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2xx body that decodes to a JSON array (not an object) is a typed error."""
    with _client(monkeypatch, _transport([], json=["unexpected"])) as client:
        with pytest.raises(NewsError):
            client.get_news(["AAPL"])


def test_normalize_article_missing_headline_raises() -> None:
    with pytest.raises(NewsError):
        normalize_article({"created_at": "2024-02-01T13:30:00Z", "symbols": ["AAPL"]})


def test_normalize_article_defaults_source_and_tolerates_sparse_item() -> None:
    article = normalize_article(
        {"headline": "Something happened", "created_at": "2024-02-01T13:30:00Z"}
    )
    assert article.source == "unknown"
    assert article.symbols == ()
    assert article.url is None
    assert article.id is None
