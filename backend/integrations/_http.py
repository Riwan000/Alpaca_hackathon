"""Shared helpers for the Alpaca data-plane integration clients.

The market-data (P3-BE-1) and news (P3-BE-2) clients both talk to
``data.alpaca.markets`` with the same key/secret auth as the trading client,
and share the same primitives: parse an RFC-3339 timestamp, format a
``start`` / ``end`` query parameter, normalise a symbol list, and run a GET
whose every failure mode collapses to one typed error. They live here so
neither client re-implements them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import Any

import httpx

# Alpaca timestamps can carry nanosecond precision (9 fractional digits) which
# :func:`datetime.fromisoformat` rejects — trim any fraction to microseconds.
_FRACTION_RE = re.compile(r"\.(\d+)")


def parse_timestamp(value: str) -> datetime:
    """Parse an Alpaca RFC-3339 timestamp into a timezone-aware :class:`datetime`."""
    text = value.strip().replace("Z", "+00:00")
    text = _FRACTION_RE.sub(lambda m: "." + m.group(1)[:6], text)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_query_date(value: datetime | date | str) -> str:
    """Format a date/datetime for an Alpaca ``start`` / ``end`` query parameter.

    Strings pass through untouched (the caller already formatted them); naive
    datetimes are assumed UTC; plain dates render as ``YYYY-MM-DD``.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.isoformat()


def join_symbols(symbols: str | Iterable[str]) -> str:
    """Normalise a symbol or iterable of symbols to a comma-separated upper-case list.

    De-duplicates while preserving first-seen order. Raises :class:`ValueError`
    when nothing usable is left so callers fail before the HTTP round-trip.
    """
    items = [symbols] if isinstance(symbols, str) else list(symbols)
    cleaned = [s.strip().upper() for s in items if s and s.strip()]
    if not cleaned:
        raise ValueError("at least one symbol is required")
    seen: dict[str, None] = {}
    for symbol in cleaned:
        seen.setdefault(symbol, None)
    return ",".join(seen)


def request_json(
    client: httpx.Client,
    path: str,
    *,
    error_cls: type[Exception],
    label: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET ``path`` and return decoded JSON, mapping every failure to ``error_cls``.

    Mirrors :meth:`backend.integrations.alpaca.client.AlpacaClient._get`: an
    upstream 4xx/5xx, a transport/timeout error, or a 2xx body that is not JSON
    all surface as a single typed exception instead of leaking ``httpx`` types
    or crashing the caller.
    """
    try:
        response = client.get(path, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise error_cls(
            f"{label} GET {path} -> {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:  # network / timeout / transport errors
        raise error_cls(f"{label} GET {path} failed: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:  # 2xx with a non-JSON body (edge/proxy HTML page)
        raise error_cls(
            f"{label} GET {path} returned a non-JSON body ({response.status_code})"
        ) from exc


def expect_object(data: Any, *, error_cls: type[Exception], label: str) -> Mapping[str, Any]:
    """Assert a decoded JSON payload is an object, else raise ``error_cls``.

    Turns an unexpected top-level array / scalar into a typed error instead of
    an ``AttributeError`` when the caller reaches for ``data.get(...)``.
    """
    if not isinstance(data, Mapping):
        raise error_cls(f"{label}: expected a JSON object, got {type(data).__name__}")
    return data
