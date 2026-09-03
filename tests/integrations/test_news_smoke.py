"""News connectivity smoke test — task P3-BE-2.

Hits the real Alpaca news feed with the credentials in ``.env``. Marked
``smoke`` so it is deselected by default; it self-skips when no Alpaca keys are
configured.

Run:  pytest -m smoke tests/integrations
"""

from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.integrations.alpaca import resolve_alpaca_config
from backend.integrations.alpaca.client import AlpacaCredentialsError
from backend.integrations.news import NewsClient

pytestmark = pytest.mark.smoke

_HELD_SYMBOL = "AAPL"


def test_fetch_news_for_held_symbol(capsys: pytest.CaptureFixture[str]) -> None:
    """`get_news([held])` returns >= 1 normalised article with the contract fields."""
    settings = get_settings()
    try:
        resolve_alpaca_config(settings)
    except AlpacaCredentialsError:
        pytest.skip("no Alpaca credentials configured")

    with NewsClient(settings) as client:
        articles = client.get_news([_HELD_SYMBOL], limit=10, max_pages=1)

    assert len(articles) >= 1, f"expected at least one article for {_HELD_SYMBOL}"
    for article in articles:
        assert article.headline
        assert article.ts.tzinfo is not None
        assert article.source

    with capsys.disabled():
        print(
            f"\n{_HELD_SYMBOL} news: {len(articles)} articles "
            f"(latest {articles[0].ts.date()}: {articles[0].headline!r})"
        )
