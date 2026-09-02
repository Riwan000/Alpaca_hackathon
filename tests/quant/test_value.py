"""Unit tests for portfolio value aggregation — task P2-BE-1.

long + short + cash → expected total; empty portfolio → cash only.
"""

from __future__ import annotations

import pytest

from backend.quant.portfolio.position import Position
from backend.quant.portfolio.value import (
    compute_portfolio_value,
    portfolio_value,
    positions_value,
)

pytestmark = pytest.mark.unit


def test_long_short_and_cash_sum_to_expected_total() -> None:
    cash = 10_000.0
    positions = [
        Position(symbol="AAPL", quantity=100, price=150.0),  # +15_000
        Position(symbol="TSLA", quantity=-50, price=200.0),  # -10_000
    ]

    result = compute_portfolio_value(cash, positions)

    assert result.long_value == pytest.approx(15_000.0)
    assert result.short_value == pytest.approx(-10_000.0)
    assert result.positions_value == pytest.approx(5_000.0)
    assert result.total_value == pytest.approx(15_000.0)
    assert portfolio_value(cash, positions) == pytest.approx(15_000.0)


def test_empty_portfolio_is_cash_only() -> None:
    result = compute_portfolio_value(25_000.0, [])

    assert result.positions_value == 0.0
    assert result.total_value == pytest.approx(25_000.0)
    assert portfolio_value(25_000.0, []) == pytest.approx(25_000.0)


def test_option_multiplier_scales_notional() -> None:
    # 2 contracts · $3.50 · 100 multiplier = $700 of long exposure
    positions = [Position(symbol="SPY_PUT", quantity=2, price=3.50, multiplier=100)]

    assert positions_value(positions) == pytest.approx(700.0)


def test_negative_price_is_rejected() -> None:
    with pytest.raises(ValueError):
        Position(symbol="AAPL", quantity=1, price=-1.0)
