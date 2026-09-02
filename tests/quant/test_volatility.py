"""Unit tests for portfolio volatility — tasks P2-BE-5, P2-BE-18.

constant returns → 0; known sample → expected annualized σ;
``portfolio_volatility`` = √(wᵀ Σ w).
"""

from __future__ import annotations

import math

import pytest

from backend.quant.risk.volatility import (
    annualize,
    covariance_matrix,
    portfolio_volatility,
    returns_volatility,
    volatility,
)

pytestmark = pytest.mark.unit


def test_constant_returns_have_zero_volatility() -> None:
    assert returns_volatility([0.01] * 10) == 0.0

    result = volatility([0.005] * 6)
    assert result.periodic == 0.0
    assert result.annualized == 0.0


def test_known_sample_matches_hand_computed_stdev() -> None:
    # mean 0.15, deviations ±0.05, sample variance 0.005 (ddof=1).
    assert returns_volatility([0.10, 0.20]) == pytest.approx(math.sqrt(0.005))


def test_volatility_annualizes_by_sqrt_of_periods() -> None:
    # alternating ±0.01 → mean 0, Σdev² = 0.0004, sample variance 0.0004/3.
    returns = [0.01, -0.01, 0.01, -0.01]

    result = volatility(returns)

    assert result.periodic == pytest.approx(math.sqrt(0.0004 / 3))
    assert result.annualized == pytest.approx(result.periodic * math.sqrt(252))
    assert result.periods_per_year == 252
    assert result.observations == 4


def test_annualize_scales_by_sqrt_periods_per_year() -> None:
    assert annualize(0.02, 4) == pytest.approx(0.04)
    with pytest.raises(ValueError):
        annualize(0.02, 0)


def test_covariance_matrix_is_symmetric_with_variance_on_the_diagonal() -> None:
    returns = {
        "A": [0.01, -0.01, 0.02, -0.02],
        "B": [0.02, -0.02, 0.04, -0.04],  # exactly 2·A
    }

    matrix = covariance_matrix(returns)

    assert matrix["A"]["B"] == pytest.approx(matrix["B"]["A"])
    assert matrix["A"]["A"] == pytest.approx(returns_volatility(returns["A"]) ** 2)
    assert matrix["A"]["B"] == pytest.approx(2 * matrix["A"]["A"])


def test_portfolio_volatility_single_asset_is_that_asset_sigma() -> None:
    cov = {"A": {"A": 0.0004}}

    assert portfolio_volatility({"A": 1.0}, cov, annualized=False) == pytest.approx(0.02)
    assert portfolio_volatility({"A": 1.0}, cov) == pytest.approx(0.02 * math.sqrt(252))


def test_portfolio_volatility_combines_uncorrelated_assets_in_quadrature() -> None:
    cov = {
        "A": {"A": 0.0004, "B": 0.0},
        "B": {"A": 0.0, "B": 0.0004},
    }

    # 0.5²·0.0004 + 0.5²·0.0004 = 0.0002
    assert portfolio_volatility(
        {"A": 0.5, "B": 0.5}, cov, annualized=False
    ) == pytest.approx(math.sqrt(0.0002))


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        volatility([])
    with pytest.raises(ValueError):
        volatility([0.01])  # need more than ddof=1 observations
    with pytest.raises(ValueError):
        portfolio_volatility({}, {})
    with pytest.raises(ValueError):
        portfolio_volatility({"A": 1.0}, {})  # no covariance row for A
