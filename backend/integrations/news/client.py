"""News client — task P3-BE-2.

A thin synchronous wrapper over the Alpaca **news** feed
(``data.alpaca.markets/v1beta1/news``) that fetches raw articles and normalises
each one to :class:`Article` — ``{headline, ts, symbols, source}`` plus a few
optional fields. An empty feed normalises to ``[]``; every upstream failure
surfaces as :class:`NewsError` and never crashes the caller.

Auth is the same Alpaca key/secret as the trading client, so this module reuses
:func:`backend.integrations.alpaca.client.resolve_alpaca_config`. The HTTP layer
is plain :mod:`httpx` for ``httpx.MockTransport`` injection in tests.
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

_NEWS_PATH = "/v1beta1/news"
_DEFAULT_TIMEOUT = 10.0
# Alpaca caps a news page at 50 items; cap the page walk so a bad
# ``next_page_token`` loop can never run unbounded.
_MAX_PAGE_LIMIT = 50
_MAX_PAGES = 5
_DEFAULT_SOURCE = "unknown"


class NewsError(RuntimeError):
    """Raised when the news API errors, is unreachable, or returns junk."""


@dataclass(frozen=True)
class Article:
    """A normalised news article / event.

    ``headline``, ``ts``, ``symbols`` and ``source`` are the contract every
    consumer relies on; the rest are best-effort passthroughs.
    """

    headline: str
    ts: datetime
    symbols: tuple[str, ...]
    source: str
    url: str | None = None
    summary: str | None = None
    id: int | None = None
    author: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the plain-dict form ``{headline, ts, symbols, source, ...}``."""
        return {
            "headline": self.headline,
            "ts": self.ts,
            "symbols": list(self.symbols),
            "source": self.source,
            "url": self.url,
            "summary": self.summary,
            "id": self.id,
        }


def normalize_article(raw: Mapping[str, Any]) -> Article:
    """Normalise one raw Alpaca news object into an :class:`Article`."""
    try:
        headline = str(raw["headline"]).strip()
        if not headline:
            raise ValueError("empty headline")
        stamp = raw.get("created_at") or raw.get("updated_at")
        if not stamp:
            raise KeyError("created_at")
        ts = parse_timestamp(str(stamp))
    except (KeyError, TypeError, ValueError) as exc:
        raise NewsError(f"malformed news item: {raw!r}") from exc

    symbols = tuple(
        str(sym).strip().upper()
        for sym in (raw.get("symbols") or [])
        if str(sym).strip()
    )
    source = str(raw.get("source") or "").strip() or _DEFAULT_SOURCE
    raw_id = raw.get("id")
    return Article(
        headline=headline,
        ts=ts,
        symbols=symbols,
        source=source,
        url=(str(raw["url"]).strip() or None) if raw.get("url") else None,
        summary=(str(raw["summary"]).strip() or None) if raw.get("summary") else None,
        id=int(raw_id) if isinstance(raw_id, (int, str)) and str(raw_id).isdigit() else None,
        author=(str(raw["author"]).strip() or None) if raw.get("author") else None,
    )


class NewsClient:
    """Synchronous client for the Alpaca news feed.

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
            "base_url": _news_base_url(cfg),
            "headers": build_auth_headers(self._config),
            "timeout": timeout,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.Client(**client_kwargs)

    @property
    def base_url(self) -> str:
        """The host every request is sent to (``data.alpaca.markets`` by default)."""
        return str(self._client.base_url)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Mapping[str, Any]:
        data = request_json(
            self._client, path, params=params, error_cls=NewsError, label="news"
        )
        return expect_object(data, error_cls=NewsError, label="news")

    def get_news(
        self,
        symbols: str | Iterable[str] | None = None,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        limit: int = _MAX_PAGE_LIMIT,
        include_content: bool = False,
        sort: str = "desc",
        max_pages: int = _MAX_PAGES,
    ) -> list[Article]:
        """Fetch and normalise articles. An empty feed returns ``[]``."""
        params: dict[str, Any] = {
            "sort": sort,
            "limit": max(1, min(int(limit), _MAX_PAGE_LIMIT)),
            "include_content": str(bool(include_content)).lower(),
        }
        if symbols:
            params["symbols"] = join_symbols(symbols)
        if start is not None:
            params["start"] = format_query_date(start)
        if end is not None:
            params["end"] = format_query_date(end)

        out: list[Article] = []
        token: str | None = None
        for _ in range(max(1, max_pages)):
            page_params = dict(params)
            if token:
                page_params["page_token"] = token
            data = self._get(_NEWS_PATH, page_params)
            for item in data.get("news") or []:
                out.append(normalize_article(item))
            token = data.get("next_page_token")
            if not token:
                break
        return out

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> NewsClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _news_base_url(settings: Settings) -> str:
    """Host root for the news feed, derived from the ``/v2`` market-data URL."""
    root = settings.alpaca_data_url.split("/v2")[0].rstrip("/")
    return root or "https://data.alpaca.markets"
