"""Option-chain connectivity smoke test — task P3-BE-3.

Hits the real Alpaca options market-data API with the credentials in ``.env``.
Marked ``smoke`` so it is deselected by default; it self-skips when no Alpaca
keys are configured.

Run:  pytest -m smoke tests/integrations/test_alpaca_options_smoke.py
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.config import get_settings
from backend.integrations.alpaca import AlpacaClient, resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError
from backend.integrations.alpaca.options import OptionChainClient, OptionChainError
from backend.integrations.market_data import MarketDataClient

pytestmark = pytest.mark.smoke

# Fallback when the paper account is flat.
_DEFAULT_SYMBOL = "SPY"
# Keep the live response small: near-dated, near-the-money contracts only.
_EXPIRY_WINDOW_DAYS = 60
_STRIKE_BAND = 0.15


def _held_equity_symbol(client: AlpacaClient) -> str:
    for position in client.get_positions():
        if str(position.get("asset_class", "us_equity")) == "us_equity":
            symbol = str(position.get("symbol", "")).strip().upper()
            if symbol:
                return symbol
    return _DEFAULT_SYMBOL


def test_pull_live_option_chain_for_held_symbol(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A live chain for a held symbol parses and carries a two-sided quote."""
    settings = get_settings()
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError:
        pytest.skip("no Alpaca credentials configured")

    with AlpacaClient(settings) as trading:
        symbol = _held_equity_symbol(trading)
    with MarketDataClient(settings) as market:
        spot = market.get_spot_price(symbol)

    today = date.today()
    with OptionChainClient(settings) as options:
        try:
            chain = options.get_chain(
                symbol,
                expiration_gte=today,
                expiration_lte=today + timedelta(days=_EXPIRY_WINDOW_DAYS),
                strike_gte=round(spot * (1 - _STRIKE_BAND), 2),
                strike_lte=round(spot * (1 + _STRIKE_BAND), 2),
                feed="indicative",
            )
        except OptionChainError as exc:  # no options listed for this underlying
            pytest.skip(f"no option chain for {symbol}: {exc}")

    if not chain:
        pytest.skip(f"no near-dated contracts returned for {symbol}")

    assert all(c.underlying == symbol for c in chain)
    assert all(c.right in {"call", "put"} for c in chain)
    assert all(c.strike > 0 for c in chain)

    quoted = [c for c in chain if c.bid is not None or c.ask is not None]
    assert quoted, f"no contract in the {symbol} chain carried a bid or ask"
    liquid = [c for c in chain if not c.illiquid]

    with capsys.disabled():
        sample = quoted[len(quoted) // 2]
        print(
            f"\n{symbol} chain (spot={spot}): {len(chain)} contracts, "
            f"{len(quoted)} quoted, {len(liquid)} liquid, "
            f"{len({c.expiry for c in chain})} expiries. "
            f"e.g. {sample.symbol} bid={sample.bid} ask={sample.ask} "
            f"delta={sample.greeks.delta} iv={sample.implied_vol}"
        )
