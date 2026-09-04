"""Alpaca REST client wrapper — task P1-BE-7.

A thin synchronous wrapper over the Alpaca *trading* REST API. Credentials are
read from the environment (:class:`backend.config.Settings`); the base URL
defaults to the paper-trading host so a misconfigured deploy cannot reach the
live-money endpoint by accident.

Only the read endpoints Phase 1 needs are implemented here
(:meth:`AlpacaClient.get_account`, :meth:`AlpacaClient.get_positions`). Order
submission arrives in a later phase and extends this class; option-chain access
lives alongside in :mod:`backend.integrations.alpaca.options` (task P3-BE-3).

The HTTP layer is plain :mod:`httpx`, so tests inject an ``httpx.MockTransport``
and assert on the outgoing auth headers / URL without a network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from backend.config import Settings, get_settings

# Alpaca's paper-trading host. Used when ``ALPACA_BASE_URL`` is unset.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"

# Header names Alpaca expects for key/secret auth.
KEY_ID_HEADER = "APCA-API-KEY-ID"
SECRET_KEY_HEADER = "APCA-API-SECRET-KEY"

_ACCOUNT_PATH = "/v2/account"
_POSITIONS_PATH = "/v2/positions"
_ORDERS_PATH = "/v2/orders"
_DEFAULT_TIMEOUT = 10.0


class AlpacaError(RuntimeError):
    """Raised when the Alpaca API returns a non-2xx response or is unreachable."""


class AlpacaCredentialsError(RuntimeError):
    """Raised when the API key / secret are not configured in the environment."""


@dataclass(frozen=True)
class AlpacaConfig:
    """Resolved connection parameters for the Alpaca trading API — no client yet."""

    api_key: str
    secret_key: str
    base_url: str
    paper: bool


def resolve_alpaca_config(settings: Settings | None = None) -> AlpacaConfig:
    """Resolve Alpaca credentials + base URL from settings.

    Raises :class:`AlpacaCredentialsError` when either the key or the secret is
    missing / blank, so callers fail fast with a clear message instead of a 403.
    """
    cfg = settings or get_settings()
    key = cfg.alpaca_api_key.get_secret_value().strip() if cfg.alpaca_api_key else ""
    secret = (
        cfg.alpaca_secret_key.get_secret_value().strip() if cfg.alpaca_secret_key else ""
    )
    if not key or not secret:
        raise AlpacaCredentialsError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set to use the Alpaca client"
        )
    return AlpacaConfig(
        api_key=key,
        secret_key=secret,
        base_url=(cfg.alpaca_base_url or PAPER_BASE_URL).rstrip("/"),
        paper=cfg.alpaca_paper,
    )


def build_auth_headers(config: AlpacaConfig) -> dict[str, str]:
    """Return the key/secret auth headers Alpaca expects on every request."""
    return {
        KEY_ID_HEADER: config.api_key,
        SECRET_KEY_HEADER: config.secret_key,
    }


class AlpacaClient:
    """Synchronous client for the Alpaca trading REST API.

    Construct it with the process :class:`Settings` (the default) or an explicit
    :class:`AlpacaConfig`. Pass ``transport`` to redirect HTTP at a mock in tests.
    Usable as a context manager so the underlying connection pool is closed.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        config: AlpacaConfig | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._config = config or resolve_alpaca_config(settings)
        client_kwargs: dict[str, Any] = {
            "base_url": self._config.base_url,
            "headers": build_auth_headers(self._config),
            "timeout": timeout,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.Client(**client_kwargs)

    @property
    def base_url(self) -> str:
        """The base URL every request is sent to (paper host by default)."""
        return str(self._client.base_url)

    @property
    def paper(self) -> bool:
        """``True`` when pointed at a paper-trading account (``ALPACA_PAPER``)."""
        return self._config.paper

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AlpacaError(
                f"Alpaca GET {path} -> {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:  # network / timeout / transport errors
            raise AlpacaError(f"Alpaca GET {path} failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:  # 2xx with a non-JSON body (edge/proxy HTML page)
            raise AlpacaError(
                f"Alpaca GET {path} returned a non-JSON body ({response.status_code})"
            ) from exc

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AlpacaError(
                f"Alpaca POST {path} -> {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:  # network / timeout / transport errors
            raise AlpacaError(f"Alpaca POST {path} failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:  # 2xx with a non-JSON body (edge/proxy HTML page)
            raise AlpacaError(
                f"Alpaca POST {path} returned a non-JSON body ({response.status_code})"
            ) from exc

    def get_account(self) -> dict[str, Any]:
        """Return the trading account object (``id``, ``account_number``, ...)."""
        return self._get(_ACCOUNT_PATH)

    def get_positions(self) -> list[dict[str, Any]]:
        """Return the list of open positions (empty list when flat)."""
        data = self._get(_POSITIONS_PATH)
        if data is None:
            return []
        if not isinstance(data, list):
            raise AlpacaError(f"expected a positions array, got {type(data).__name__}")
        return data

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST one order to ``/v2/orders`` and return the created order object.

        ``payload`` is a fully-formed Alpaca order body — a single-leg order or
        an ``order_class: "mleg"`` combo (see
        :mod:`backend.integrations.alpaca.orders`). Any non-2xx response, a
        transport error, or a non-JSON body surfaces as :class:`AlpacaError`.
        """
        data = self._post(_ORDERS_PATH, payload)
        if not isinstance(data, dict):
            raise AlpacaError(f"expected an order object, got {type(data).__name__}")
        return data

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> AlpacaClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
