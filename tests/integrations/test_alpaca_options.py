"""Tests for the Alpaca option-chain client — task P3-BE-3.

No network: an ``httpx.MockTransport`` captures each outgoing request and feeds
back a recorded Alpaca options-snapshot payload. Covers OCC symbol parsing,
strike / expiry / greeks extraction, the illiquid-strike flag, query-param
mapping, pagination, and the "upstream 5xx -> typed error, no crash" contract.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from backend.config import Settings
from backend.integrations.alpaca import (
    OptionChainClient,
    OptionChainError,
    OptionContract,
    OptionGreeks,
    is_illiquid,
    normalize_right,
    parse_occ_symbol,
    parse_option_snapshot,
)

_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/db",
    "ALPACA_API_KEY": "PKTEST1234567890",
    "ALPACA_SECRET_KEY": "secret-abcdefghijklmnop",
    "ALPACA_DATA_URL": "https://data.alpaca.markets/v2",
    "ALPACA_PAPER": "true",
}

# A recorded SPY options-snapshot response: two expiries, calls + puts, one
# deep-OTM put with a dead two-sided market (the illiquid strike).
_CHAIN_RESPONSE = {
    "snapshots": {
        "SPY260320P00450000": {
            "latestQuote": {
                "ap": 5.30, "as": 25, "ax": "C",
                "bp": 5.10, "bs": 20, "bx": "C",
                "t": "2026-03-02T20:59:59.123456Z",
            },
            "latestTrade": {"p": 5.20, "s": 3, "t": "2026-03-02T20:55:01Z", "x": "C"},
            "greeks": {"delta": -0.42, "gamma": 0.031, "theta": -0.058, "vega": 0.21, "rho": -0.09},
            "impliedVolatility": 0.1834,
        },
        "SPY260320C00470000": {
            "latestQuote": {
                "ap": 6.05, "as": 18, "bp": 5.85, "bs": 22, "t": "2026-03-02T20:59:59Z",
            },
            "latestTrade": {"p": 5.95, "s": 1, "t": "2026-03-02T20:50:00Z"},
            "greeks": {"delta": 0.48, "gamma": 0.029, "theta": -0.061, "vega": 0.20, "rho": 0.08},
            "impliedVolatility": 0.1712,
        },
        "SPY260320P00400000": {
            "latestQuote": {
                "ap": 0.0, "as": 0, "bp": 0.0, "bs": 0, "t": "2026-03-02T20:59:59Z",
            },
            "latestTrade": {"p": 0.02, "s": 1, "t": "2026-02-11T18:03:22Z"},
            "greeks": {"delta": -0.01, "gamma": 0.002, "theta": -0.004, "vega": 0.01, "rho": -0.001},
            "impliedVolatility": 0.4102,
        },
        "SPY260618P00450000": {
            "latestQuote": {
                "ap": 9.40, "as": 12, "bp": 9.05, "bs": 15, "t": "2026-03-02T20:59:59Z",
            },
            "latestTrade": {"p": 9.25, "s": 2, "t": "2026-03-02T19:44:10Z"},
            "greeks": {"delta": -0.44, "gamma": 0.019, "theta": -0.032, "vega": 0.35, "rho": -0.18},
            "impliedVolatility": 0.1955,
        },
    },
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


def _client(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> OptionChainClient:
    return OptionChainClient(_settings(monkeypatch), transport=transport)


# --- OCC symbol parsing --------------------------------------------------------


def test_parse_occ_symbol_extracts_underlying_expiry_strike_right() -> None:
    assert parse_occ_symbol("SPY260320P00450000") == ("SPY", date(2026, 3, 20), 450.0, "put")
    assert parse_occ_symbol("aapl260116c00200000") == (
        "AAPL", date(2026, 1, 16), 200.0, "call",
    )
    # Fractional strike: 6.5 -> 00006500.
    assert parse_occ_symbol("F270115C00006500")[2] == 6.5


@pytest.mark.parametrize(
    "bad",
    ["SPY", "SPY260320X00450000", "260320P00450000", "SPY26032AP00450000", ""],
)
def test_parse_occ_symbol_rejects_malformed_ids(bad: str) -> None:
    with pytest.raises(OptionChainError):
        parse_occ_symbol(bad)


# --- recorded chain -> typed contracts ---------------------------------------


def test_get_chain_parses_recorded_response_into_typed_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recorded chain becomes sorted :class:`OptionContract`s with parsed greeks."""
    with _client(monkeypatch, _transport([], json=_CHAIN_RESPONSE)) as client:
        chain = client.get_chain("SPY")

    assert len(chain) == 4
    assert all(isinstance(c, OptionContract) for c in chain)
    # Sorted by (expiry, strike, right).
    assert [(c.expiry, c.strike, c.right) for c in chain] == [
        (date(2026, 3, 20), 400.0, "put"),
        (date(2026, 3, 20), 450.0, "put"),
        (date(2026, 3, 20), 470.0, "call"),
        (date(2026, 6, 18), 450.0, "put"),
    ]

    atm = next(c for c in chain if c.strike == 450.0 and c.expiry == date(2026, 3, 20))
    assert atm.underlying == "SPY"
    assert atm.bid == 5.10 and atm.ask == 5.30
    assert atm.bid_size == 20.0 and atm.ask_size == 25.0
    assert atm.last_price == 5.20
    assert atm.mid == 5.2 and atm.spread == pytest.approx(0.2)
    assert atm.implied_vol == 0.1834
    assert atm.greeks == OptionGreeks(
        delta=-0.42, gamma=0.031, theta=-0.058, vega=0.21, rho=-0.09
    )
    assert atm.quote_ts is not None and atm.quote_ts.tzinfo is not None


def test_get_chain_extracts_distinct_strikes_and_expiries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(monkeypatch, _transport([], json=_CHAIN_RESPONSE)) as client:
        expiries = client.get_expiries("SPY")
        strikes = client.get_strikes("SPY", expiration="2026-03-20")

    assert expiries == [date(2026, 3, 20), date(2026, 6, 18)]
    assert strikes == [400.0, 450.0, 470.0]


def test_illiquid_strike_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deep-OTM put with a 0/0 market is flagged; the ATM strike is not."""
    with _client(monkeypatch, _transport([], json=_CHAIN_RESPONSE)) as client:
        chain = client.get_chain("SPY")

    by_key = {(c.expiry, c.strike, c.right): c for c in chain}
    dead = by_key[(date(2026, 3, 20), 400.0, "put")]
    live = by_key[(date(2026, 3, 20), 450.0, "put")]
    assert dead.illiquid is True
    assert live.illiquid is False


@pytest.mark.parametrize(
    "bid,ask,bid_size,ask_size,expected",
    [
        (5.10, 5.30, 20, 25, False),   # healthy two-sided market
        (None, 5.30, 20, 25, True),    # no bid
        (5.10, None, 20, 25, True),    # no ask
        (0.0, 0.0, 0, 0, True),        # dead market
        (5.10, 5.30, 0, 25, True),     # zero size on the bid
        (1.00, 3.00, 10, 10, True),    # spread 2.00 on a 2.00 mid -> 100% > 50%
        (1.90, 2.10, 10, 10, False),   # 0.20 spread on a 2.00 mid -> 10%
        (3.00, 1.00, 10, 10, True),    # crossed market (ask below bid)
    ],
)
def test_is_illiquid_thresholds(
    bid: float | None,
    ask: float | None,
    bid_size: float,
    ask_size: float,
    expected: bool,
) -> None:
    contract = OptionContract(
        symbol="SPY260320P00450000",
        underlying="SPY",
        expiry=date(2026, 3, 20),
        strike=450.0,
        right="put",
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
    )
    assert is_illiquid(contract) is expected


def test_parse_option_snapshot_tolerates_missing_quote_and_greeks() -> None:
    """A snapshot with no quote / greeks parses to an illiquid, greek-less contract."""
    contract = parse_option_snapshot("SPY260320P00450000", {"latestTrade": {"p": 0.01}})
    assert contract.bid is None and contract.ask is None
    assert contract.greeks == OptionGreeks()
    assert contract.illiquid is True


def test_normalize_right_rejects_non_string_with_typed_error() -> None:
    """A non-str ``right=`` raises :class:`OptionChainError`, not ``AttributeError``."""
    assert normalize_right("Puts") == "put"
    with pytest.raises(OptionChainError):
        normalize_right(None)  # type: ignore[arg-type]
    with pytest.raises(OptionChainError):
        normalize_right("straddle")


# --- request shaping ---------------------------------------------------------


def test_get_chain_sends_expected_path_query_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_CHAIN_RESPONSE)) as client:
        client.get_chain(
            "spy",
            expiration="2026-03-20",
            right="P",
            strike_gte=400,
            strike_lte=500,
            feed="indicative",
        )

    assert len(requests) == 1
    sent = requests[0]
    assert sent.url.path == "/v1beta1/options/snapshots/SPY"
    assert sent.url.params["expiration_date"] == "2026-03-20"
    assert sent.url.params["type"] == "put"
    assert sent.url.params["strike_price_gte"] == "400.0"
    assert sent.url.params["strike_price_lte"] == "500.0"
    assert sent.url.params["feed"] == "indicative"
    # limit defaults to the largest page Alpaca serves, so the page cap bounds
    # total contracts rather than silently truncating at 100/page.
    assert sent.url.params["limit"] == "1000"
    assert sent.headers["APCA-API-KEY-ID"] == "PKTEST1234567890"
    assert sent.headers["APCA-API-SECRET-KEY"] == "secret-abcdefghijklmnop"


@pytest.mark.parametrize(
    "payload", [{"snapshots": {}, "next_page_token": None}, {"snapshots": None}]
)
def test_get_chain_empty_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    with _client(monkeypatch, _transport([], json=payload)) as client:
        assert client.get_chain("SPY") == []


def test_get_chain_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    """``next_page_token`` is walked until exhausted and snapshots are concatenated."""
    snaps = _CHAIN_RESPONSE["snapshots"]
    keys = list(snaps)
    pages = {
        None: {
            "snapshots": {k: snaps[k] for k in keys[:2]},
            "next_page_token": "PAGE-2",
        },
        "PAGE-2": {
            "snapshots": {k: snaps[k] for k in keys[2:]},
            "next_page_token": None,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("page_token")])

    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, handler=handler)) as client:
        chain = client.get_chain("SPY")

    assert len(requests) == 2
    assert len(chain) == 4


def test_get_chain_raises_when_page_cap_hit_with_token_still_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A still-live ``next_page_token`` at the page cap is an error, not silent truncation."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "snapshots": {"SPY260320P00450000": _CHAIN_RESPONSE["snapshots"]["SPY260320P00450000"]},
                "next_page_token": "ALWAYS-MORE",
            },
        )

    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, handler=handler)) as client:
        with pytest.raises(OptionChainError, match="not exhausted"):
            client.get_chain("SPY", max_pages=3)
    assert len(requests) == 3  # walked exactly the cap, then raised


def test_upstream_5xx_raises_typed_error_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(
        monkeypatch, _transport([], status=503, json={"message": "unavailable"})
    ) as client:
        with pytest.raises(OptionChainError):
            client.get_chain("SPY")


def test_2xx_non_json_body_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with _client(monkeypatch, _transport([], handler=handler)) as client:
        with pytest.raises(OptionChainError):
            client.get_chain("SPY")


def test_non_object_payload_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, _transport([], json=["unexpected"])) as client:
        with pytest.raises(OptionChainError):
            client.get_chain("SPY")


def test_snapshots_not_object_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(
        monkeypatch, _transport([], json={"snapshots": ["nope"]})
    ) as client:
        with pytest.raises(OptionChainError):
            client.get_chain("SPY")


def test_blank_underlying_raises_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    with _client(monkeypatch, _transport(requests, json=_CHAIN_RESPONSE)) as client:
        with pytest.raises(OptionChainError):
            client.get_chain("   ")
    assert requests == []
