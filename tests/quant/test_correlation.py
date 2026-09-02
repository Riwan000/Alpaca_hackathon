"""Unit tests for correlation — tasks P2-BE-7, P2-BE-18.

self-correlation 1.0; negated series → −1.0; affine transforms preserve |ρ|;
matrix symmetric with a unit diagonal.
"""

from __future__ import annotations

import pytest

from backend.quant.risk.correlation import correlation, correlation_matrix

pytestmark = pytest.mark.unit

SERIES = [1.0, 2.0, 3.0, 4.0, 5.0]


def test_self_correlation_is_one() -> None:
    assert correlation(SERIES, SERIES) == pytest.approx(1.0)


def test_negated_series_correlates_minus_one() -> None:
    assert correlation(SERIES, [-x for x in SERIES]) == pytest.approx(-1.0)


def test_affine_transform_preserves_perfect_correlation() -> None:
    assert correlation(SERIES, [3 * x + 7 for x in SERIES]) == pytest.approx(1.0)
    assert correlation(SERIES, [-2 * x + 1 for x in SERIES]) == pytest.approx(-1.0)


def test_orthogonal_series_have_zero_correlation() -> None:
    xs = [1.0, -1.0, 1.0, -1.0]
    ys = [1.0, 1.0, -1.0, -1.0]

    assert correlation(xs, ys) == pytest.approx(0.0)


def test_correlation_matrix_is_symmetric_with_unit_diagonal() -> None:
    matrix = correlation_matrix(
        {
            "A": list(SERIES),
            "B": [-x for x in SERIES],
            "C": [3 * x + 7 for x in SERIES],
        }
    )

    assert matrix.names == ("A", "B", "C")
    assert matrix.get("A", "A") == 1.0
    assert matrix.get("B", "B") == 1.0
    assert matrix.get("A", "B") == pytest.approx(-1.0)
    assert matrix.get("A", "C") == pytest.approx(1.0)
    assert matrix.get("A", "B") == pytest.approx(matrix.get("B", "A"))


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])  # constant series
    with pytest.raises(ValueError):
        correlation([1.0, 2.0], [1.0, 2.0, 3.0])  # length mismatch
    with pytest.raises(ValueError):
        correlation_matrix({})  # empty
    with pytest.raises(ValueError):
        correlation_matrix({"A": [1.0, 1.0, 1.0]})  # lone constant series
    with pytest.raises(ValueError):
        correlation_matrix({"A": list(SERIES), "B": [2.0, 2.0, 2.0, 2.0, 2.0]})
