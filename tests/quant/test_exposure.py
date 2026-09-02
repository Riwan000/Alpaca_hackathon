"""Unit tests for portfolio exposure — task P2-BE-2.

per-position = qty·price·multiplier; gross ≠ net when a short is present.
"""

from __future__ import annotations

import pytest

from backend.quant.portfolio.exposure import (
    compute_exposure,
    gross_exposure,
    net_exposure,
    position_exposure,
)
from backend.quant.portfolio.position import Position

pytestmark = pytest.mark.unit


def test_position_exposure_is_qty_price_multiplier() -> None:
    equity = Position(symbol="AAPL", quantity=100, price=150.0)
    option = Position(symbol="SPY_PUT", quantity=-3, price=4.0, multiplier=100)

    assert position_exposure(equity) == pytest.approx(15_000.0)
    assert position_exposure(option) == pytest.approx(-1_200.0)


def test_gross_equals_net_for_a_long_only_book() -> None:
    positions = [
        Position(symbol="AAPL", quantity=100, price=150.0),
        Position(symbol="MSFT", quantity=50, price=400.0),
    ]

    assert gross_exposure(positions) == pytest.approx(35_000.0)
    assert gross_exposure(positions) == pytest.approx(net_exposure(positions))


def test_gross_exceeds_net_when_a_short_is_present() -> None:
    positions = [
        Position(symbol="AAPL", quantity=100, price=150.0),  # +15_000
        Position(symbol="TSLA", quantity=-40, price=200.0),  # -8_000
    ]

    breakdown = compute_exposure(positions)

    assert breakdown.long_exposure == pytest.approx(15_000.0)
    assert breakdown.short_exposure == pytest.approx(-8_000.0)
    assert breakdown.net_exposure == pytest.approx(7_000.0)
    assert breakdown.gross_exposure == pytest.approx(23_000.0)
    assert breakdown.gross_exposure != pytest.approx(breakdown.net_exposure)
    assert {pe.symbol for pe in breakdown.per_position} == {"AAPL", "TSLA"}


def test_empty_book_has_zero_exposure() -> None:
    breakdown = compute_exposure([])

    assert breakdown.gross_exposure == 0.0
    assert breakdown.net_exposure == 0.0
    assert breakdown.per_position == ()
