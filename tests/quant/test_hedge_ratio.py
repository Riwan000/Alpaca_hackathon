"""Unit tests for hedge ratio — task P2-BE-8.

full hedge → 1.0; no hedge → 0.0; drift = target − current;
``rebalance_notional`` = drift · |exposure|.
"""

from __future__ import annotations

import pytest

from backend.quant.risk.hedge_ratio import (
    assess_hedge,
    hedge_drift,
    hedge_ratio,
    rebalance_notional,
)

pytestmark = pytest.mark.unit


def test_full_hedge_is_ratio_one_regardless_of_sign() -> None:
    assert hedge_ratio(5_000.0, 5_000.0) == pytest.approx(1.0)
    assert hedge_ratio(-5_000.0, 5_000.0) == pytest.approx(1.0)


def test_no_hedge_is_ratio_zero() -> None:
    assert hedge_ratio(0.0, 5_000.0) == 0.0


def test_flat_book_is_ratio_zero() -> None:
    assert hedge_ratio(1_000.0, 0.0) == 0.0


def test_over_hedge_exceeds_one() -> None:
    assert hedge_ratio(7_500.0, 5_000.0) == pytest.approx(1.5)


def test_drift_is_target_minus_current() -> None:
    assert hedge_drift(0.4, 1.0) == pytest.approx(0.6)
    assert hedge_drift(1.0, 0.5) == pytest.approx(-0.5)


def test_rebalance_notional_is_drift_times_absolute_exposure() -> None:
    assert rebalance_notional(10_000.0, 0.4, 1.0) == pytest.approx(6_000.0)
    assert rebalance_notional(10_000.0, 1.2, 1.0) == pytest.approx(-2_000.0)


def test_assess_hedge_reports_current_target_drift_and_rebalance() -> None:
    assessment = assess_hedge(
        hedge_notional=4_000.0, exposure_notional=10_000.0, target_ratio=1.0
    )

    assert assessment.current_ratio == pytest.approx(0.4)
    assert assessment.target_ratio == 1.0
    assert assessment.drift == pytest.approx(0.6)
    assert assessment.rebalance_notional == pytest.approx(6_000.0)
    assert not assessment.within_tolerance(0.05)
    assert assessment.within_tolerance(0.6)


def test_assess_hedge_full_hedge_has_zero_drift() -> None:
    assert assess_hedge(10_000.0, 10_000.0, 1.0).drift == pytest.approx(0.0)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        assess_hedge(1.0, 1.0, -0.1)  # negative target ratio
    with pytest.raises(ValueError):
        assess_hedge(1.0, 1.0, 1.0).within_tolerance(-0.01)  # negative tolerance
