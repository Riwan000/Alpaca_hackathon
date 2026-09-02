"""Alpaca trading API integration — task P1-BE-7."""

from backend.integrations.alpaca.client import (
    KEY_ID_HEADER,
    PAPER_BASE_URL,
    SECRET_KEY_HEADER,
    AlpacaClient,
    AlpacaConfig,
    AlpacaCredentialsError,
    AlpacaError,
    build_auth_headers,
    resolve_alpaca_config,
)

__all__ = [
    "KEY_ID_HEADER",
    "PAPER_BASE_URL",
    "SECRET_KEY_HEADER",
    "AlpacaClient",
    "AlpacaConfig",
    "AlpacaCredentialsError",
    "AlpacaError",
    "build_auth_headers",
    "resolve_alpaca_config",
]
