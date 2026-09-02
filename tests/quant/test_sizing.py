"""Unit tests for position sizing — task P2-BE-14 (Issue #65).

Key invariants verified:
- contracts = floor(budget / (premium * multiplier))
- zero budget → 0 contracts
- result is never negative
- invalid inputs are rejected with ValueError
"""

from __future__ import annotations

import pytest

from backend.quant.sizing import (
    SizingResult,
    contracts_from_budget,
    size_position,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Core formula: floor(budget / (premium * multiplier))
# ---------------------------------------------------------------------------

BUDGET = 5_000.0
PREMIUM = 2.50
MULTIPLIER = 100.0
#: floor(5000 / (2.50 * 100)) = floor(5000 / 250) = floor(20.0) = 20
EXPECTED_CONTRACTS = 20


def test_contracts_from_budget_basic() -> None:
    assert contracts_from_budget(BUDGET, PREMIUM, MULTIPLIER) == EXPECTED_CONTRACTS


def test_contracts_uses_floor_not_round() -> None:
    # budget / (premium * multiplier) = 5100 / 250 = 20.4 → floor = 20
    assert contracts_from_budget(5_100.0, PREMIUM, MULTIPLIER) == 20


def test_contracts_exactly_fills_budget() -> None:
    # budget = 20 * 2.50 * 100 = 5000 exactly → 20 contracts
    assert contracts_from_budget(5_000.0, PREMIUM, MULTIPLIER) == 20


def test_contracts_defaults_to_option_multiplier_100() -> None:
    # floor(5000 / (2.50 * 100)) = 20
    assert contracts_from_budget(BUDGET, PREMIUM) == EXPECTED_CONTRACTS


# ---------------------------------------------------------------------------
# Zero budget → 0 contracts
# ---------------------------------------------------------------------------


def test_zero_budget_returns_zero_contracts() -> None:
    assert contracts_from_budget(0.0, PREMIUM, MULTIPLIER) == 0


def test_size_position_zero_budget_returns_zero() -> None:
    result = size_position(0.0, PREMIUM, MULTIPLIER)

    assert result.contracts == 0
    assert result.cash_required == 0.0
    assert result.budget_residual == 0.0
    assert result.budget_utilisation == 0.0


# ---------------------------------------------------------------------------
# Result is never negative
# ---------------------------------------------------------------------------


def test_contracts_never_negative_tiny_budget() -> None:
    # Budget too small for even one contract
    result = contracts_from_budget(1.0, 10.0, 100.0)
    assert result == 0
    assert result >= 0


def test_size_position_contracts_never_negative() -> None:
    result = size_position(0.01, 50.0, 100.0)
    assert result.contracts >= 0


# ---------------------------------------------------------------------------
# SizingResult fields
# ---------------------------------------------------------------------------


def test_size_position_reports_correct_fields() -> None:
    result = size_position(BUDGET, PREMIUM, MULTIPLIER)

    assert isinstance(result, SizingResult)
    assert result.contracts == EXPECTED_CONTRACTS
    # 20 * 2.50 * 100 = 5000.00
    assert result.cash_required == pytest.approx(5_000.0)
    assert result.budget == BUDGET
    assert result.budget_residual == pytest.approx(0.0)
    assert result.budget_utilisation == pytest.approx(1.0)


def test_size_position_residual_when_budget_not_fully_used() -> None:
    # floor(5100 / 250) = 20 contracts; cash = 5000; residual = 100
    result = size_position(5_100.0, PREMIUM, MULTIPLIER)

    assert result.contracts == 20
    assert result.cash_required == pytest.approx(5_000.0)
    assert result.budget_residual == pytest.approx(100.0)
    assert result.budget_utilisation < 1.0


def test_size_position_budget_utilisation_is_fraction() -> None:
    result = size_position(BUDGET, PREMIUM, MULTIPLIER)
    assert 0.0 <= result.budget_utilisation <= 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_high_premium_relative_to_budget_gives_zero_contracts() -> None:
    # premium * multiplier = 500 * 100 = 50000 > budget 1000 → 0
    assert contracts_from_budget(1_000.0, 500.0, 100.0) == 0


def test_very_small_premium_gives_large_contract_count() -> None:
    # floor(10000 / (0.01 * 100)) = floor(10000 / 1) = 10000
    assert contracts_from_budget(10_000.0, 0.01, 100.0) == 10_000


def test_non_standard_multiplier() -> None:
    # floor(6000 / (3.0 * 50)) = floor(6000 / 150) = 40
    assert contracts_from_budget(6_000.0, 3.0, 50.0) == 40


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("budget", [-0.01, -1_000.0])
def test_negative_budget_is_rejected(budget: float) -> None:
    with pytest.raises(ValueError, match="budget"):
        contracts_from_budget(budget, PREMIUM, MULTIPLIER)


@pytest.mark.parametrize("premium", [0.0, -1.0])
def test_non_positive_premium_is_rejected(premium: float) -> None:
    with pytest.raises(ValueError, match="premium"):
        contracts_from_budget(BUDGET, premium, MULTIPLIER)


@pytest.mark.parametrize("multiplier", [0.0, -100.0])
def test_non_positive_multiplier_is_rejected(multiplier: float) -> None:
    with pytest.raises(ValueError, match="multiplier"):
        contracts_from_budget(BUDGET, PREMIUM, multiplier)


def test_size_position_propagates_validation_errors() -> None:
    with pytest.raises(ValueError):
        size_position(-1.0, PREMIUM, MULTIPLIER)
    with pytest.raises(ValueError):
        size_position(BUDGET, 0.0, MULTIPLIER)
