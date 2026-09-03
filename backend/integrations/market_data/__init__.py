"""Market-data integration — task P3-BE-1."""

from backend.integrations.market_data.client import (
    INDEX_PROXY_SYMBOLS,
    Bar,
    MarketDataClient,
    MarketDataError,
    Trade,
    parse_bar,
    resolve_index_symbol,
)

__all__ = [
    "INDEX_PROXY_SYMBOLS",
    "Bar",
    "MarketDataClient",
    "MarketDataError",
    "Trade",
    "parse_bar",
    "resolve_index_symbol",
]
