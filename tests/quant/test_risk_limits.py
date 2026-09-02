"""Unit tests for risk limit checks — task P2-BE-15 (Issue #66).

Key invariants verified:
- over-limit → violation with a human-readable reason
- exactly at limit → pass
- all three checks (hedge ratio, notional, budget) covered
- check_all_limits aggregates results correctly
- invalid inputs are rejected with ValueError
"""

from __future__ import annotations

import pytest

from backend.quant.risk_limits import (
    LimitReport,
    LimitResult,
    check_all_limits,
    check_budget,
    check_hedge_ratio,
    check_notional,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# check_hedge_ratio
# ---------------------------------------------------------------------------


def test_hedge_ratio_under_limit_passes() -> None:
    result = check_hedge_ratio(proposed_ratio=0.8, max_ratio=1.0)
    assert result.passed is True
    assert result.reason == ""
    assert result.violated is False


def test_hedge_ratio_exactly_at_limit_passes() -> None:
    result = check_hedge_ratio(proposed_ratio=1.0, max_ratio=1.0)
    assert result.passed is True


def test_hedge_ratio_over_limit_fails_with_reason() -> None:
    result = check_hedge_ratio(proposed_ratio=1.2, max_ratio=1.0)
    assert result.passed is False
    assert result.violated is True
    assert "hedge ratio" in result.reason
    assert "1.2" in result.reason or "1.0" in result.reason


def test_hedge_ratio_zero_proposed_always_passes() -> None:
    assert check_hedge_ratio(proposed_ratio=0.0, max_ratio=0.0).passed is True
    assert check_hedge_ratio(proposed_ratio=0.0, max_ratio=1.0).passed is True


def test_hedge_ratio_negative_proposed_is_rejected() -> None:
    with pytest.raises(ValueError, match="proposed_ratio"):
        check_hedge_ratio(proposed_ratio=-0.1, max_ratio=1.0)


def test_hedge_ratio_negative_max_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_ratio"):
        check_hedge_ratio(proposed_ratio=0.5, max_ratio=-1.0)


# ---------------------------------------------------------------------------
# check_notional
# ---------------------------------------------------------------------------


def test_notional_under_limit_passes() -> None:
    result = check_notional(proposed_notional=8_000.0, max_notional=10_000.0)
    assert result.passed is True
    assert result.reason == ""


def test_notional_exactly_at_limit_passes() -> None:
    result = check_notional(proposed_notional=10_000.0, max_notional=10_000.0)
    assert result.passed is True


def test_notional_over_limit_fails_with_reason() -> None:
    result = check_notional(proposed_notional=12_000.0, max_notional=10_000.0)
    assert result.passed is False
    assert "notional" in result.reason
    assert "12,000" in result.reason or "12000" in result.reason.replace(",", "")


def test_notional_signed_negative_uses_magnitude() -> None:
    # Selling 12000 notional still breaches a 10000 cap
    result = check_notional(proposed_notional=-12_000.0, max_notional=10_000.0)
    assert result.passed is False


def test_notional_negative_max_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_notional"):
        check_notional(proposed_notional=5_000.0, max_notional=-1.0)


def test_notional_zero_proposed_always_passes() -> None:
    assert check_notional(proposed_notional=0.0, max_notional=0.0).passed is True
    assert check_notional(proposed_notional=0.0, max_notional=10_000.0).passed is True


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


def test_budget_under_limit_passes() -> None:
    result = check_budget(cash_cost=3_000.0, budget=5_000.0)
    assert result.passed is True
    assert result.reason == ""


def test_budget_exactly_at_limit_passes() -> None:
    result = check_budget(cash_cost=5_000.0, budget=5_000.0)
    assert result.passed is True


def test_budget_over_limit_fails_with_reason() -> None:
    result = check_budget(cash_cost=6_000.0, budget=5_000.0)
    assert result.passed is False
    assert "budget" in result.reason or "cost" in result.reason


def test_budget_zero_cost_always_passes() -> None:
    assert check_budget(cash_cost=0.0, budget=0.0).passed is True
    assert check_budget(cash_cost=0.0, budget=5_000.0).passed is True


def test_budget_negative_cost_is_rejected() -> None:
    with pytest.raises(ValueError, match="cash_cost"):
        check_budget(cash_cost=-1.0, budget=5_000.0)


def test_budget_negative_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="budget"):
        check_budget(cash_cost=1_000.0, budget=-1.0)


# ---------------------------------------------------------------------------
# check_all_limits — aggregate helper
# ---------------------------------------------------------------------------


def _all_within() -> LimitReport:
    return check_all_limits(
        proposed_ratio=0.8,
        max_ratio=1.0,
        proposed_notional=8_000.0,
        max_notional=10_000.0,
        cash_cost=3_000.0,
        budget=5_000.0,
    )


def test_all_limits_pass_when_all_within() -> None:
    report = _all_within()
    assert isinstance(report, LimitReport)
    assert report.passed is True
    assert report.violations == []
    assert report.violation_reasons == []


def test_all_limits_fail_when_hedge_ratio_breached() -> None:
    report = check_all_limits(
        proposed_ratio=1.5,   # over
        max_ratio=1.0,
        proposed_notional=8_000.0,
        max_notional=10_000.0,
        cash_cost=3_000.0,
        budget=5_000.0,
    )
    assert report.passed is False
    assert len(report.violations) == 1
    assert report.violation_reasons[0] != ""


def test_all_limits_fail_when_notional_breached() -> None:
    report = check_all_limits(
        proposed_ratio=0.8,
        max_ratio=1.0,
        proposed_notional=15_000.0,  # over
        max_notional=10_000.0,
        cash_cost=3_000.0,
        budget=5_000.0,
    )
    assert report.passed is False
    assert len(report.violations) == 1


def test_all_limits_fail_when_budget_breached() -> None:
    report = check_all_limits(
        proposed_ratio=0.8,
        max_ratio=1.0,
        proposed_notional=8_000.0,
        max_notional=10_000.0,
        cash_cost=7_000.0,   # over
        budget=5_000.0,
    )
    assert report.passed is False
    assert len(report.violations) == 1


def test_all_limits_can_report_multiple_violations() -> None:
    report = check_all_limits(
        proposed_ratio=2.0,    # over
        max_ratio=1.0,
        proposed_notional=20_000.0,  # over
        max_notional=10_000.0,
        cash_cost=8_000.0,    # over
        budget=5_000.0,
    )
    assert report.passed is False
    assert len(report.violations) == 3
    assert len(report.violation_reasons) == 3


def test_all_limits_exactly_at_every_limit_passes() -> None:
    report = check_all_limits(
        proposed_ratio=1.0,
        max_ratio=1.0,
        proposed_notional=10_000.0,
        max_notional=10_000.0,
        cash_cost=5_000.0,
        budget=5_000.0,
    )
    assert report.passed is True
    assert report.violations == []
