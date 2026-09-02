"""Unit tests for shared numeric helpers — task P2-BE-16 (Issue #67).

Key invariants verified:
- returns_from_prices matches a hand calculation (simple percentage returns)
- log_returns_from_prices matches a hand calculation
- TRADING_DAYS_PER_YEAR is a named constant (not a bare 252 inline literal)
- CALENDAR_DAYS_PER_YEAR is a named constant (not a bare 365 inline literal)
- annualize_factor, annualize, deannualize are consistent
- Input validation raises ValueError on bad inputs
"""

from __future__ import annotations

import math

import pytest

from backend.quant.helpers import (
    CALENDAR_DAYS_PER_YEAR,
    MONTHS_PER_YEAR,
    TRADING_DAYS_PER_YEAR,
    WEEKS_PER_YEAR,
    annualize,
    annualize_factor,
    deannualize,
    log_returns_from_prices,
    returns_from_prices,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------


def test_trading_days_per_year_is_named_constant() -> None:
    """TRADING_DAYS_PER_YEAR must be the canonical 252, importable by name."""
    assert TRADING_DAYS_PER_YEAR == 252


def test_calendar_days_per_year_is_named_constant() -> None:
    """CALENDAR_DAYS_PER_YEAR must be the canonical 365, importable by name."""
    assert CALENDAR_DAYS_PER_YEAR == 365.0


def test_weeks_per_year_is_named_constant() -> None:
    assert WEEKS_PER_YEAR == 52


def test_months_per_year_is_named_constant() -> None:
    assert MONTHS_PER_YEAR == 12


# ---------------------------------------------------------------------------
# returns_from_prices
# ---------------------------------------------------------------------------


def test_returns_from_prices_basic_hand_calculation() -> None:
    """(110 - 100) / 100 = 0.1 and (99 - 110) / 110 ≈ -0.1."""
    prices = [100.0, 110.0, 99.0]
    returns = returns_from_prices(prices)

    assert len(returns) == 2
    assert returns[0] == pytest.approx(0.1)
    assert returns[1] == pytest.approx(-11.0 / 110.0)


def test_returns_from_prices_flat_series_is_zero() -> None:
    """Constant prices → zero returns."""
    prices = [50.0, 50.0, 50.0]
    returns = returns_from_prices(prices)

    assert all(r == pytest.approx(0.0) for r in returns)


def test_returns_from_prices_length_is_one_less_than_prices() -> None:
    prices = [10.0, 20.0, 30.0, 25.0]
    assert len(returns_from_prices(prices)) == len(prices) - 1


def test_returns_from_prices_single_step_up() -> None:
    # 200 / 100 - 1 = 1.0 (100% gain)
    assert returns_from_prices([100.0, 200.0]) == pytest.approx([1.0])


def test_returns_from_prices_single_step_down() -> None:
    # 50 / 100 - 1 = -0.5 (50% loss)
    assert returns_from_prices([100.0, 50.0]) == pytest.approx([-0.5])


def test_returns_from_prices_result_matches_by_hand() -> None:
    """Verify against hand-computed values for a 5-element series."""
    prices = [100.0, 105.0, 103.0, 108.0, 106.0]
    expected = [
        (105.0 - 100.0) / 100.0,   #  0.05
        (103.0 - 105.0) / 105.0,   # -0.019047...
        (108.0 - 103.0) / 103.0,   #  0.048543...
        (106.0 - 108.0) / 108.0,   # -0.018518...
    ]
    result = returns_from_prices(prices)

    assert len(result) == len(expected)
    for r, e in zip(result, expected):
        assert r == pytest.approx(e, rel=1e-9)


def test_returns_from_prices_two_elements_gives_one_return() -> None:
    assert len(returns_from_prices([10.0, 12.0])) == 1


def test_returns_from_prices_rejects_fewer_than_two_prices() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        returns_from_prices([100.0])
    with pytest.raises(ValueError, match="at least 2"):
        returns_from_prices([])


def test_returns_from_prices_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError, match="positive"):
        returns_from_prices([100.0, 0.0, 110.0])
    with pytest.raises(ValueError, match="positive"):
        returns_from_prices([100.0, -5.0, 110.0])


# ---------------------------------------------------------------------------
# log_returns_from_prices
# ---------------------------------------------------------------------------


def test_log_returns_from_prices_basic() -> None:
    """ln(110/100) and ln(99/110) hand-checked."""
    prices = [100.0, 110.0, 99.0]
    returns = log_returns_from_prices(prices)

    assert len(returns) == 2
    assert returns[0] == pytest.approx(math.log(110.0 / 100.0))
    assert returns[1] == pytest.approx(math.log(99.0 / 110.0))


def test_log_returns_from_prices_one_e_fold_gives_one() -> None:
    """ln(e * 100 / 100) = 1."""
    prices = [100.0, math.e * 100.0]
    result = log_returns_from_prices(prices)
    assert result[0] == pytest.approx(1.0)


def test_log_returns_from_prices_flat_series_is_zero() -> None:
    returns = log_returns_from_prices([50.0, 50.0, 50.0])
    assert all(r == pytest.approx(0.0) for r in returns)


def test_log_returns_from_prices_length_is_one_less() -> None:
    prices = [10.0, 12.0, 11.0, 13.0]
    assert len(log_returns_from_prices(prices)) == len(prices) - 1


def test_log_returns_rejects_fewer_than_two_prices() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        log_returns_from_prices([100.0])


def test_log_returns_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError, match="positive"):
        log_returns_from_prices([100.0, 0.0])


# ---------------------------------------------------------------------------
# annualize_factor
# ---------------------------------------------------------------------------


def test_annualize_factor_for_trading_days() -> None:
    """sqrt(252) is the standard daily-to-annual vol scaler."""
    assert annualize_factor(TRADING_DAYS_PER_YEAR) == pytest.approx(math.sqrt(252))


def test_annualize_factor_for_calendar_days() -> None:
    assert annualize_factor(CALENDAR_DAYS_PER_YEAR) == pytest.approx(math.sqrt(365.0))


def test_annualize_factor_of_one_is_one() -> None:
    assert annualize_factor(1) == pytest.approx(1.0)


def test_annualize_factor_of_four_is_two() -> None:
    # sqrt(4) = 2
    assert annualize_factor(4) == pytest.approx(2.0)


def test_annualize_factor_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="periods_per_year"):
        annualize_factor(0)
    with pytest.raises(ValueError, match="periods_per_year"):
        annualize_factor(-1)


# ---------------------------------------------------------------------------
# annualize / deannualize
# ---------------------------------------------------------------------------


def test_annualize_defaults_to_trading_days() -> None:
    periodic = 0.01  # 1% per day
    expected = 0.01 * math.sqrt(252)
    assert annualize(periodic) == pytest.approx(expected)


def test_annualize_with_explicit_periods() -> None:
    periodic = 0.05
    assert annualize(periodic, 52) == pytest.approx(0.05 * math.sqrt(52))


def test_deannualize_is_inverse_of_annualize() -> None:
    periodic = 0.01
    annual = annualize(periodic, TRADING_DAYS_PER_YEAR)
    recovered = deannualize(annual, TRADING_DAYS_PER_YEAR)
    assert recovered == pytest.approx(periodic)


def test_deannualize_defaults_to_trading_days() -> None:
    annual = 0.20  # 20% annualised vol
    expected = 0.20 / math.sqrt(252)
    assert deannualize(annual) == pytest.approx(expected)


def test_annualize_zero_is_zero() -> None:
    assert annualize(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Integration: constants are consumed correctly by downstream modules
# ---------------------------------------------------------------------------


def test_volatility_module_uses_trading_days_constant() -> None:
    """The volatility module's DEFAULT_PERIODS_PER_YEAR must equal TRADING_DAYS_PER_YEAR."""
    from backend.quant.risk.volatility import DEFAULT_PERIODS_PER_YEAR

    assert DEFAULT_PERIODS_PER_YEAR == TRADING_DAYS_PER_YEAR


def test_black_scholes_module_uses_calendar_days_constant() -> None:
    """The Black-Scholes module's DAYS_PER_YEAR must equal CALENDAR_DAYS_PER_YEAR."""
    from backend.quant.greeks.black_scholes import DAYS_PER_YEAR

    assert DAYS_PER_YEAR == CALENDAR_DAYS_PER_YEAR
