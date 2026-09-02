"""Unit tests for drawdown / high-water mark — tasks P2-BE-4, P2-BE-17.

known equity curve → expected max DD; flat curve → 0; new high → HWM updates.
"""

from __future__ import annotations

import pytest

from backend.quant.portfolio.drawdown import (
    compute_drawdown,
    drawdown_series,
    high_water_marks,
    max_drawdown,
)

pytestmark = pytest.mark.unit


def test_known_curve_has_expected_max_drawdown() -> None:
    # hwm:  100  120  120  120  200  200  250
    # dd:     0    0 -.50 -.33    0 -.25    0   → deepest is 50% off the 120 peak
    curve = [100.0, 120.0, 60.0, 80.0, 200.0, 150.0, 250.0]

    result = compute_drawdown(curve)

    assert max_drawdown(curve) == pytest.approx(0.5)
    assert result.max_drawdown == pytest.approx(0.5)
    assert result.peak_index == 1
    assert result.trough_index == 2
    assert result.high_water_mark == pytest.approx(250.0)
    assert result.current_drawdown == pytest.approx(0.0)


def test_flat_curve_has_zero_drawdown() -> None:
    curve = [100.0] * 5

    assert max_drawdown(curve) == 0.0
    assert drawdown_series(curve) == [0.0] * 5
    assert compute_drawdown(curve).max_drawdown == 0.0


def test_monotonically_rising_curve_has_zero_drawdown() -> None:
    assert max_drawdown([10.0, 20.0, 30.0, 40.0]) == 0.0


def test_high_water_mark_updates_on_a_new_high() -> None:
    curve = [100.0, 90.0, 130.0, 110.0]

    assert high_water_marks(curve) == [100.0, 100.0, 130.0, 130.0]

    result = compute_drawdown(curve)
    assert result.high_water_mark == pytest.approx(130.0)
    assert result.current_drawdown == pytest.approx((110.0 - 130.0) / 130.0)


def test_empty_curve_raises() -> None:
    with pytest.raises(ValueError):
        compute_drawdown([])
    with pytest.raises(ValueError):
        max_drawdown([])
