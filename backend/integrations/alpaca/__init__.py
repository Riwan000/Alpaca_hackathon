"""Alpaca trading API integration — tasks P1-BE-7 and P3-BE-3."""

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
from backend.integrations.alpaca.options import (
    MAX_RELATIVE_SPREAD,
    OptionChainClient,
    OptionChainError,
    OptionContract,
    OptionGreeks,
    is_illiquid,
    normalize_right,
    parse_occ_symbol,
    parse_option_snapshot,
)

__all__ = [
    "KEY_ID_HEADER",
    "MAX_RELATIVE_SPREAD",
    "PAPER_BASE_URL",
    "SECRET_KEY_HEADER",
    "AlpacaClient",
    "AlpacaConfig",
    "AlpacaCredentialsError",
    "AlpacaError",
    "OptionChainClient",
    "OptionChainError",
    "OptionContract",
    "OptionGreeks",
    "build_auth_headers",
    "is_illiquid",
    "normalize_right",
    "parse_occ_symbol",
    "parse_option_snapshot",
    "resolve_alpaca_config",
]
