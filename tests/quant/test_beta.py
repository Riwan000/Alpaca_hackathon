"""Unit tests for portfolio beta — tasks P2-BE-6, P2-BE-18.

series identical to benchmark → 1.0; uncorrelated → ~0; scaled → the scale;
``portfolio_beta`` combines component betas by weight.
"""

from __future__ import annotations

import pytest

from backend.quant.risk.beta import beta, compute_beta, portfolio_beta

pytestmark = pytest.mark.unit

BENCHMARK = [0.02, -0.01, 0.03, -0.02, 0.01]


def test_series_identical_to_benchmark_has_beta_one() -> None:
    assert beta(BENCHMARK, BENCHMARK) == pytest.approx(1.0)


def test_scaled_series_has_beta_equal_to_the_scale() -> None:
    doubled = [2 * r for r in BENCHMARK]

    assert beta(doubled, BENCHMARK) == pytest.approx(2.0)


def test_mirrored_series_has_beta_minus_one() -> None:
    mirrored = [-r for r in BENCHMARK]

    assert beta(mirrored, BENCHMARK) == pytest.approx(-1.0)


def test_uncorrelated_series_has_beta_zero() -> None:
    benchmark = [1.0, -1.0, 1.0, -1.0]
    asset = [1.0, 1.0, -1.0, -1.0]  # zero sample covariance with benchmark

    assert beta(asset, benchmark) == pytest.approx(0.0)


def test_compute_beta_exposes_its_components() -> None:
    result = compute_beta(BENCHMARK, BENCHMARK)

    assert result.beta == pytest.approx(1.0)
    assert result.covariance == pytest.approx(result.benchmark_variance)
    assert result.observations == len(BENCHMARK)


def test_portfolio_beta_is_the_weighted_sum_of_component_betas() -> None:
    components = {
        "A": list(BENCHMARK),  # beta 1.0
        "B": [2 * r for r in BENCHMARK],  # beta 2.0
    }

    combined = portfolio_beta(components, {"A": 0.5, "B": 0.5}, BENCHMARK)

    assert combined == pytest.approx(1.5)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        beta([0.01, 0.02, 0.03], [0.05, 0.05, 0.05])  # benchmark has zero variance
    with pytest.raises(ValueError):
        beta([0.01, 0.02], BENCHMARK)  # length mismatch
    with pytest.raises(ValueError):
        portfolio_beta({}, {}, BENCHMARK)  # empty weights
    with pytest.raises(ValueError):
        portfolio_beta({"A": list(BENCHMARK)}, {"B": 1.0}, BENCHMARK)  # unknown symbol
