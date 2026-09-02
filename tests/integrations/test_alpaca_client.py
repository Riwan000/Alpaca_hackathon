"""Tests for the Alpaca client wrapper — task P1-BE-7.

No network: an ``httpx.MockTransport`` captures each outgoing request so we can
assert on the auth headers and the paper base URL, and feed canned JSON back to
:meth:`AlpacaClient.get_account` / :meth:`AlpacaClient.get_positions`.
"""

from __future__ import annotations

import httpx
import pytest

from backend.config import Settings
from backend.integrations.alpaca import (
    KEY_ID_HEADER,
    PAPER_BASE_URL,
    SECRET_KEY_HEADER,
    AlpacaClient,
    AlpacaCredentialsError,
    AlpacaError,
    build_auth_headers,
    resolve_alpaca_config,
)

_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/db",
    "ALPACA_API_KEY": "PKTEST1234567890",
    "ALPACA_SECRET_KEY": "secret-abcdefghijklmnop",
    "ALPACA_BASE_URL": PAPER_BASE_URL,
    "ALPACA_PAPER": "true",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key, value in {**_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def _recording_transport(
    sink: list[httpx.Request],
    *,
    status: int = 200,
    json: object = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return httpx.Response(status, json=json if json is not None else {})

    return httpx.MockTransport(handler)


def test_build_auth_headers_uses_alpaca_header_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper sends key/secret under Alpaca's documented header names."""
    config = resolve_alpaca_config(_settings(monkeypatch))
    headers = build_auth_headers(config)

    assert headers == {
        KEY_ID_HEADER: "PKTEST1234567890",
        SECRET_KEY_HEADER: "secret-abcdefghijklmnop",
    }


def test_client_targets_paper_base_url_with_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every request goes to the paper host and carries both auth headers."""
    requests: list[httpx.Request] = []
    transport = _recording_transport(requests, json={"id": "acct-1"})

    with AlpacaClient(_settings(monkeypatch), transport=transport) as client:
        assert client.base_url.rstrip("/") == PAPER_BASE_URL
        assert client.paper is True
        client.get_account()

    assert len(requests) == 1
    sent = requests[0]
    assert str(sent.url) == f"{PAPER_BASE_URL}/v2/account"
    assert sent.url.host == "paper-api.alpaca.markets"
    assert sent.headers[KEY_ID_HEADER] == "PKTEST1234567890"
    assert sent.headers[SECRET_KEY_HEADER] == "secret-abcdefghijklmnop"


def test_get_account_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_account`` returns the decoded account object."""
    transport = _recording_transport(
        [], json={"id": "904837e3-3b76", "account_number": "PA123456", "status": "ACTIVE"}
    )
    with AlpacaClient(_settings(monkeypatch), transport=transport) as client:
        account = client.get_account()

    assert account["id"] == "904837e3-3b76"
    assert account["account_number"] == "PA123456"


def test_get_positions_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_positions`` returns a list, including the empty (flat) case."""
    payload = [{"symbol": "AAPL", "qty": "10"}, {"symbol": "SPY", "qty": "5"}]
    with AlpacaClient(
        _settings(monkeypatch), transport=_recording_transport([], json=payload)
    ) as client:
        assert client.get_positions() == payload

    with AlpacaClient(
        _settings(monkeypatch), transport=_recording_transport([], json=[])
    ) as client:
        assert client.get_positions() == []


def test_non_2xx_response_raises_alpaca_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """An upstream 4xx/5xx is surfaced as a typed :class:`AlpacaError`."""
    transport = _recording_transport([], status=403, json={"message": "forbidden"})
    with AlpacaClient(_settings(monkeypatch), transport=transport) as client:
        with pytest.raises(AlpacaError):
            client.get_account()


def test_2xx_non_json_body_raises_alpaca_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 with an HTML/edge-proxy body is surfaced as :class:`AlpacaError`."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with AlpacaClient(
        _settings(monkeypatch), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(AlpacaError):
            client.get_account()


def test_get_positions_rejects_non_array_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 object body where an array is expected raises, not silent key list."""
    transport = _recording_transport([], json={"message": "unexpected"})
    with AlpacaClient(_settings(monkeypatch), transport=transport) as client:
        with pytest.raises(AlpacaError):
            client.get_positions()


def test_missing_credentials_raise_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank key or secret fails fast with :class:`AlpacaCredentialsError`."""
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-abcdefghijklmnop")

    with pytest.raises(AlpacaCredentialsError):
        resolve_alpaca_config(Settings(_env_file=None))
    with pytest.raises(AlpacaCredentialsError):
        AlpacaClient(Settings(_env_file=None))
