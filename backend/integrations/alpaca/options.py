"""Alpaca option-chain access — task P3-BE-3.

A thin synchronous wrapper over the Alpaca **options** market-data API
(``data.alpaca.markets/v1beta1/options/snapshots/{underlying}``). It pulls the
snapshot chain for an underlying and normalises every leg to a typed
:class:`OptionContract` — OCC symbol, expiry, strike and right parsed from the
contract id; bid/ask/sizes from ``latestQuote``; last print from
``latestTrade``; ``delta/gamma/theta/vega/rho`` from ``greeks``; and the
implied vol. Each contract exposes :pyattr:`OptionContract.illiquid` so a
consumer can drop strikes with no real two-sided market.

Auth is the same Alpaca key/secret as the trading client, so this module reuses
:func:`backend.integrations.alpaca.client.resolve_alpaca_config` and
:func:`~backend.integrations.alpaca.client.build_auth_headers`. The HTTP layer is
plain :mod:`httpx` so tests inject an ``httpx.MockTransport`` and feed a recorded
chain without a network call. Every upstream failure surfaces as
:class:`OptionChainError` — an upstream 5xx never crashes the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from backend.config import Settings, get_settings
from backend.integrations._http import expect_object, parse_timestamp, request_json
from backend.integrations.alpaca.client import build_auth_headers, resolve_alpaca_config

_SNAPSHOTS_PATH = "/v1beta1/options/snapshots/{underlying}"
_DEFAULT_TIMEOUT = 10.0
# Alpaca caps an options snapshot page at 1 000 contracts; cap the page walk so a
# bad ``next_page_token`` loop can never run unbounded.
_MAX_PAGE_LIMIT = 1_000
_MAX_PAGES = 20

# An OCC option symbol is ``<root><YYMMDD><C|P><strike * 1000, 8 digits>`` — the
# fixed 15-character tail is date(6) + right(1) + strike(8).
_OCC_TAIL_LEN = 15
_OCC_STRIKE_MULTIPLIER = 1000

# A contract whose bid/ask spread is wider than this fraction of its mid price
# has no usable two-sided market even when both sides are quoted.
MAX_RELATIVE_SPREAD = 0.5

_RIGHT_BY_CODE = {"C": "call", "P": "put"}
_RIGHT_ALIASES = {
    "c": "call",
    "call": "call",
    "calls": "call",
    "p": "put",
    "put": "put",
    "puts": "put",
}


class OptionChainError(RuntimeError):
    """Raised when the option-chain API errors, is unreachable, or returns junk."""


@dataclass(frozen=True)
class OptionGreeks:
    """First-order risk sensitivities for one contract (any field may be absent)."""

    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None


@dataclass(frozen=True)
class OptionContract:
    """One normalised leg of an option chain.

    ``symbol``, ``underlying``, ``expiry``, ``strike`` and ``right`` are the
    contract identity (parsed from the OCC id). The quote fields are best-effort:
    an illiquid strike often has no bid, no ask, or zero size on one side.
    """

    symbol: str
    underlying: str
    expiry: date
    strike: float
    right: str  # "call" | "put"
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    last_price: float | None = None
    implied_vol: float | None = None
    greeks: OptionGreeks = field(default_factory=OptionGreeks)
    quote_ts: datetime | None = None

    @property
    def mid(self) -> float | None:
        """Mid price, or ``None`` when either side is unquoted."""
        if self.bid is None or self.ask is None:
            return None
        return round((self.bid + self.ask) / 2, 6)

    @property
    def spread(self) -> float | None:
        """Absolute bid/ask spread, or ``None`` when either side is unquoted."""
        if self.bid is None or self.ask is None:
            return None
        return round(self.ask - self.bid, 6)

    @property
    def illiquid(self) -> bool:
        """``True`` when this strike has no usable two-sided market."""
        return is_illiquid(self)


def normalize_right(value: str) -> str:
    """Map ``"C"``/``"call"``/``"PUT"``/... to the canonical ``"call"`` / ``"put"``."""
    if not isinstance(value, str):
        raise OptionChainError(f"option right must be a string, got {type(value).__name__}")
    try:
        return _RIGHT_ALIASES[value.strip().lower()]
    except KeyError as exc:
        raise OptionChainError(f"unknown option right {value!r}") from exc


def parse_occ_symbol(symbol: str) -> tuple[str, date, float, str]:
    """Split an OCC option id into ``(underlying, expiry, strike, right)``.

    ``"SPY260320P00450000"`` -> ``("SPY", date(2026, 3, 20), 450.0, "put")``.
    Raises :class:`OptionChainError` on anything that is not a well-formed id.
    """
    text = symbol.strip().upper()
    if len(text) <= _OCC_TAIL_LEN:
        raise OptionChainError(f"malformed OCC option symbol: {symbol!r}")
    root = text[:-_OCC_TAIL_LEN]
    date_digits = text[-_OCC_TAIL_LEN:-9]
    right_code = text[-9]
    strike_digits = text[-8:]
    if not (root and date_digits.isdigit() and strike_digits.isdigit()):
        raise OptionChainError(f"malformed OCC option symbol: {symbol!r}")
    if right_code not in _RIGHT_BY_CODE:
        raise OptionChainError(f"malformed OCC option symbol: {symbol!r}")
    try:
        expiry = date(
            2000 + int(date_digits[:2]), int(date_digits[2:4]), int(date_digits[4:6])
        )
    except ValueError as exc:
        raise OptionChainError(f"malformed OCC option symbol: {symbol!r}") from exc
    strike = int(strike_digits) / _OCC_STRIKE_MULTIPLIER
    return root, expiry, strike, _RIGHT_BY_CODE[right_code]


def is_illiquid(contract: OptionContract) -> bool:
    """A strike is illiquid when it lacks a real two-sided market.

    That is: a missing or non-positive bid or ask, zero size on either side, a
    crossed quote (ask below bid), or a spread wider than
    :data:`MAX_RELATIVE_SPREAD` of the mid price.
    """
    bid, ask = contract.bid, contract.ask
    if bid is None or ask is None:
        return True
    if bid <= 0 or ask <= 0:
        return True
    if not contract.bid_size or not contract.ask_size:
        return True
    if ask < bid:  # crossed / locked market
        return True
    mid = (bid + ask) / 2
    return (ask - bid) / mid > MAX_RELATIVE_SPREAD


def _as_float(raw: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in raw and raw[key] is not None:
            try:
                return float(raw[key])
            except (TypeError, ValueError):
                return None
    return None


def _parse_greeks(raw: Any) -> OptionGreeks:
    if not isinstance(raw, Mapping):
        return OptionGreeks()
    return OptionGreeks(
        delta=_as_float(raw, "delta"),
        gamma=_as_float(raw, "gamma"),
        theta=_as_float(raw, "theta"),
        vega=_as_float(raw, "vega"),
        rho=_as_float(raw, "rho"),
    )


def parse_option_snapshot(occ_symbol: str, raw: Mapping[str, Any]) -> OptionContract:
    """Normalise one ``{OCC: snapshot}`` entry into an :class:`OptionContract`."""
    if not isinstance(raw, Mapping):
        raise OptionChainError(f"snapshot for {occ_symbol} is not an object: {raw!r}")
    underlying, expiry, strike, right = parse_occ_symbol(occ_symbol)

    quote = raw.get("latestQuote") or raw.get("latest_quote") or {}
    trade = raw.get("latestTrade") or raw.get("latest_trade") or {}
    if not isinstance(quote, Mapping) or not isinstance(trade, Mapping):
        raise OptionChainError(f"malformed snapshot for {occ_symbol}: {raw!r}")

    quote_ts_raw = quote.get("t")
    try:
        quote_ts = parse_timestamp(str(quote_ts_raw)) if quote_ts_raw else None
    except ValueError as exc:
        raise OptionChainError(f"malformed quote timestamp for {occ_symbol}") from exc

    return OptionContract(
        symbol=occ_symbol.strip().upper(),
        underlying=underlying,
        expiry=expiry,
        strike=strike,
        right=right,
        bid=_as_float(quote, "bp", "bid_price"),
        ask=_as_float(quote, "ap", "ask_price"),
        bid_size=_as_float(quote, "bs", "bid_size"),
        ask_size=_as_float(quote, "as", "ask_size"),
        last_price=_as_float(trade, "p", "price"),
        implied_vol=_as_float(raw, "impliedVolatility", "implied_volatility"),
        greeks=_parse_greeks(raw.get("greeks")),
        quote_ts=quote_ts,
    )


def _options_base_url(settings: Settings) -> str:
    """Host root for the options feed, derived from the ``/v2`` market-data URL."""
    root = settings.alpaca_data_url.split("/v2")[0].rstrip("/")
    return root or "https://data.alpaca.markets"


class OptionChainClient:
    """Synchronous client for the Alpaca option-chain snapshot API.

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
            "base_url": _options_base_url(cfg),
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
            self._client, path, params=params, error_cls=OptionChainError, label="option-chain"
        )
        return expect_object(data, error_cls=OptionChainError, label="option-chain")

    def get_chain(
        self,
        underlying: str,
        *,
        expiration: date | str | None = None,
        expiration_gte: date | str | None = None,
        expiration_lte: date | str | None = None,
        right: str | None = None,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
        feed: str | None = None,
        limit: int | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> list[OptionContract]:
        """Return the option chain for ``underlying`` as sorted typed contracts.

        Contracts are ordered by ``(expiry, strike, right)``. ``next_page_token``
        is walked to the end; if the chain is still not exhausted after
        ``max_pages`` requests of :data:`_MAX_PAGE_LIMIT` contracts each, an
        :class:`OptionChainError` is raised rather than a silently truncated
        chain being returned — narrow the query with ``expiration`` / ``strike``
        filters. An empty chain returns ``[]``; every upstream failure raises
        :class:`OptionChainError`.
        """
        sym = underlying.strip().upper()
        if not sym:
            raise OptionChainError("an underlying symbol is required")

        params: dict[str, Any] = {}
        if expiration is not None:
            params["expiration_date"] = _fmt_date(expiration)
        if expiration_gte is not None:
            params["expiration_date_gte"] = _fmt_date(expiration_gte)
        if expiration_lte is not None:
            params["expiration_date_lte"] = _fmt_date(expiration_lte)
        if right is not None:
            params["type"] = normalize_right(right)
        if strike_gte is not None:
            params["strike_price_gte"] = float(strike_gte)
        if strike_lte is not None:
            params["strike_price_lte"] = float(strike_lte)
        if feed is not None:
            params["feed"] = feed
        # Default to the largest page Alpaca serves so the ``max_pages`` guard is
        # a ceiling on total contracts, not an accidental 100-per-page cliff.
        requested = _MAX_PAGE_LIMIT if limit is None else int(limit)
        params["limit"] = max(1, min(requested, _MAX_PAGE_LIMIT))

        path = _SNAPSHOTS_PATH.format(underlying=sym)
        pages = max(1, max_pages)
        out: list[OptionContract] = []
        token: str | None = None
        for _ in range(pages):
            page_params = dict(params)
            if token:
                page_params["page_token"] = token
            data = self._get(path, page_params)
            snapshots = data.get("snapshots") or {}
            if not isinstance(snapshots, Mapping):
                raise OptionChainError(
                    f"expected a snapshots object keyed by OCC symbol, "
                    f"got {type(snapshots).__name__}"
                )
            for occ_symbol, snap in snapshots.items():
                out.append(parse_option_snapshot(str(occ_symbol), snap))
            token = data.get("next_page_token")
            if not token:
                break
        else:
            raise OptionChainError(
                f"option chain for {sym} not exhausted after {pages} pages of "
                f"{params['limit']} contracts; narrow the query with "
                f"expiration / strike filters or raise max_pages"
            )
        out.sort(key=lambda c: (c.expiry, c.strike, c.right))
        return out

    def get_expiries(self, underlying: str, **filters: Any) -> list[date]:
        """Return the sorted distinct expiries available for ``underlying``."""
        seen = {c.expiry for c in self.get_chain(underlying, **filters)}
        return sorted(seen)

    def get_strikes(
        self, underlying: str, *, expiration: date | str, **filters: Any
    ) -> list[float]:
        """Return the sorted distinct strikes for ``underlying`` at ``expiration``."""
        chain = self.get_chain(underlying, expiration=expiration, **filters)
        return sorted({c.strike for c in chain})

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> OptionChainClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _fmt_date(value: date | str) -> str:
    """Format a date for an Alpaca ``expiration_date*`` query parameter."""
    if isinstance(value, str):
        return value
    return value.isoformat()
