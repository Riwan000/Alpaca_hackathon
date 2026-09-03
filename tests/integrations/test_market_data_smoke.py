"""Market-data connectivity smoke test — task P3-BE-1.

Hits the real Alpaca market-data API with the credentials in ``.env``. Marked
``smoke`` so it is deselected by default; it self-skips when no Alpaca keys are
configured.

Run:  pytest -m smoke tests/integrations
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import get_settings
from backend.integrations.alpaca import resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError
from backend.integrations.market_data import MarketDataClient

pytestmark = pytest.mark.smoke


def test_fetch_spy_bars_last_30_days(capsys: pytest.CaptureFixture[str]) -> None:
    """`get_bars("SPY", ...)` returns at least one typed daily bar for the last 30 days."""
    settings = get_settings()
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError:
        pytest.skip("no Alpaca credentials configured")

    start = datetime.now(timezone.utc) - timedelta(days=30)
    with MarketDataClient(settings) as client:
        bars = client.get_bars("SPY", timeframe="1Day", start=start)

    assert bars, "expected at least one SPY daily bar in the last 30 days"
    assert all(b.symbol == "SPY" and b.close > 0 for b in bars)
    assert bars == sorted(bars, key=lambda b: b.timestamp)

    with capsys.disabled():
        print(
            f"\nSPY: {len(bars)} daily bars over 30d "
            f"(last {bars[-1].timestamp.date()} close={bars[-1].close})"
        )
