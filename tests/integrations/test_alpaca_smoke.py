"""Alpaca connectivity smoke test — task P1-BE-8.

Hits the real paper-trading account with the credentials in ``.env``. Marked
``smoke`` so it is deselected by default; it self-skips when no Alpaca keys are
configured.

Run:  pytest -m smoke tests/integrations
"""

from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.integrations.alpaca import AlpacaClient, resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError

pytestmark = pytest.mark.smoke


def test_alpaca_account_and_positions(capsys: pytest.CaptureFixture[str]) -> None:
    """`get_account()` returns an id and `get_positions()` returns a list."""
    settings = get_settings()
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError:
        pytest.skip("no Alpaca paper credentials configured")

    with AlpacaClient(settings) as client:
        account = client.get_account()
        positions = client.get_positions()

    assert account.get("id"), "account response is missing an id"
    assert isinstance(positions, list)

    account_number = account.get("account_number", "<unknown>")
    with capsys.disabled():
        print(
            f"\nAlpaca paper account: {account_number} "
            f"(status={account.get('status')}, open positions={len(positions)})"
        )
