"""Unit tests for portfolio concentration — task P2-BE-3.

single holding → HHI 1.0; N equal holdings → 1/N.
"""

from __future__ import annotations

import pytest

from backend.quant.portfolio.concentration import (
    compute_concentration,
    hhi,
    top_n_weight,
    weights,
)
from backend.quant.portfolio.position import Position

pytestmark = pytest.mark.unit


def test_single_holding_has_hhi_one() -> None:
    positions = [Position(symbol="AAPL", quantity=100, price=150.0)]

    assert hhi(positions) == pytest.approx(1.0)
    assert weights(positions) == {"AAPL": pytest.approx(1.0)}


@pytest.mark.parametrize("n", [2, 3, 4, 10])
def test_n_equal_holdings_have_hhi_one_over_n(n: int) -> None:
    positions = [
        Position(symbol=f"S{i}", quantity=10, price=100.0) for i in range(n)
    ]

    assert hhi(positions) == pytest.approx(1.0 / n)


def test_top_n_weight_sums_the_largest_holdings() -> None:
    positions = [
        Position(symbol="BIG", quantity=60, price=100.0),  # 6_000 → 0.6
        Position(symbol="MID", quantity=30, price=100.0),  # 3_000 → 0.3
        Position(symbol="SML", quantity=10, price=100.0),  # 1_000 → 0.1
    ]

    assert top_n_weight(positions, 1) == pytest.approx(0.6)
    assert top_n_weight(positions, 2) == pytest.approx(0.9)
    assert top_n_weight(positions, 3) == pytest.approx(1.0)

    profile = compute_concentration(positions, top_ns=(1, 2))
    assert profile.weights[0] == ("BIG", pytest.approx(0.6))
    assert dict(profile.top_n)[1] == pytest.approx(0.6)
    assert profile.effective_holdings == pytest.approx(1.0 / profile.hhi)


def test_shorts_count_toward_concentration_by_absolute_size() -> None:
    positions = [
        Position(symbol="LONG", quantity=50, price=100.0),  # |5_000|
        Position(symbol="SHORT", quantity=-50, price=100.0),  # |5_000|
    ]

    assert hhi(positions) == pytest.approx(0.5)


def test_empty_portfolio_has_zero_hhi() -> None:
    assert hhi([]) == 0.0
    assert weights([]) == {}


def test_non_positive_n_is_rejected() -> None:
    with pytest.raises(ValueError):
        top_n_weight([Position(symbol="AAPL", quantity=1, price=1.0)], 0)
