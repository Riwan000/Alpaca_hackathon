"""Risk-engine aggregator tests — task P5-BE-7 (BRD §19–20).

The aggregator runs every deterministic hard check over one proposed hypothesis
and folds the per-check outcomes into a single result:

* the result lists *every* check with its pass/fail and the reason behind it —
  a checklist, not just a boolean;
* any hard fail flips the overall verdict to ``REJECT`` while the passing checks
  stay on the list;
* multiple breaches are all reported, each with its own violation code;
* a soft ``CheckOutcome(warning=True)`` does not block — its reason is routed to
  ``.warnings``;
* ``limits`` is threaded only to the checks whose signature accepts it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.agents.risk import (
    RiskEngineLimits,
    ViolationCode,
    aggregate_risk,
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
    run_limit_checks,
)
from backend.agents.risk.aggregate import DEFAULT_CHECKS, AggregateRiskResult
from backend.agents.risk.engine import CheckOutcome
from backend.models.common import OptionLeg
from backend.models.enums import (
    HedgeAction,
    OptionRight,
    OrderSide,
    RiskVerdict,
    StrategyType,
)
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskCheck
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-7"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)

# the P5-BE-1/2 hard limits — used on their own for the aggregation-mechanics
# tests so they stay independent of the full registry's composition.
_LIMIT_CHECKS = (
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
)
_LIMIT_NAMES = [
    "hedge_budget",
    "max_hedge_ratio",
    "max_notional",
    "position_limit",
]
_ALL_NAMES = _LIMIT_NAMES + [
    "buying_power",
    "liquidity",
    "contract_validity",
    "expiration_window",
    "net_delta_bounds",
    "multileg_consistency",
    "price_band",
]


# --------------------------------------------------------------------------- #
# synthetic context / hypothesis for the mechanics tests
# --------------------------------------------------------------------------- #


def _context(
    *,
    total_value: float = 100_000.0,
    target_hedge_ratio: float | None = None,
    aapl_shares: float = 100.0,
    cycle_id: str = _CYCLE,
) -> HedgeContext:
    positions = []
    if aapl_shares:
        positions.append(
            {
                "symbol": "AAPL",
                "qty": aapl_shares,
                "avg_price": 150.0,
                "market_value": aapl_shares * 150.0,
                "asset_class": "EQUITY",
                "side": "BUY",
            }
        )
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": total_value / 4,
                "positions": positions,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
                "target_hedge_ratio": target_hedge_ratio,
            },
        }
    )


def _leg(
    *,
    underlying: str = "AAPL",
    strike: float = 145.0,
    quantity: int = 1,
    side: OrderSide = OrderSide.BUY,
    right: OptionRight = OptionRight.PUT,
) -> OptionLeg:
    return OptionLeg(
        underlying=underlying,
        right=right,
        side=side,
        strike=strike,
        expiration=date(2026, 10, 3),
        quantity=quantity,
    )


def _hypothesis(
    *,
    hedge_ratio: float | None = 0.5,
    cost: float = 250.0,
    legs: tuple[OptionLeg, ...] = (_leg(),),
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=hedge_ratio),
        rationale="synthetic hypothesis for the aggregator tests",
    )


# --------------------------------------------------------------------------- #
# golden context — a genuinely clean plan for the full-registry tests
# --------------------------------------------------------------------------- #


def _golden_context() -> HedgeContext:
    return HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))


def _clean_put(*, cost: float = 315.0, **overrides) -> StrategyHypothesis:
    """A protective put that lines up with the golden context's 145 candidate."""
    ctx = _golden_context()
    params = {
        "cycle_id": ctx.cycle_id,
        "strategy": StrategyType.PROTECTIVE_PUT,
        "action": HedgeAction.NEW_HEDGE,
        "viable": True,
        "legs": [
            OptionLeg(
                underlying="AAPL",
                right=OptionRight.PUT,
                side=OrderSide.BUY,
                strike=145.0,
                expiration=date(2026, 10, 3),
                quantity=1,
            )
        ],
        "cost": cost,
        "hedge_metrics": HedgeMetrics(hedge_ratio=0.5),
        "rationale": "clean protective put for the full-registry tests",
    }
    params.update(overrides)
    return StrategyHypothesis(**params)


# --------------------------------------------------------------------------- #
# the full DEFAULT_CHECKS registry
# --------------------------------------------------------------------------- #


def test_default_registry_is_the_eleven_p5_be_1_6_checks() -> None:
    assert len(DEFAULT_CHECKS) == 11

    result = aggregate_risk(_clean_put(), _golden_context())

    assert [c.name for c in result.checks] == _ALL_NAMES
    assert all(isinstance(c, RiskCheck) for c in result.checks)


def test_a_genuinely_clean_plan_passes_every_check() -> None:
    result = aggregate_risk(_clean_put(), _golden_context())

    assert result.passed is True
    assert result.verdict is RiskVerdict.APPROVE
    assert result.failures == ()
    assert result.violations == []
    assert all(c.passed for c in result.checks)
    assert all(c.detail for c in result.checks)  # every row carries a reason


def test_full_checklist_is_visible_on_a_reject() -> None:
    # a 1_000_000 debit blows the budget (and buying power) but nothing else.
    result = aggregate_risk(_clean_put(cost=1_000_000.0), _golden_context())

    assert result.verdict is RiskVerdict.REJECT
    assert [c.name for c in result.checks] == _ALL_NAMES  # all 11 still listed
    by_name = {c.name: c for c in result.checks}
    assert by_name["hedge_budget"].passed is False
    assert by_name["contract_validity"].passed is True  # specific, not blanket
    assert by_name["multileg_consistency"].passed is True
    assert ViolationCode.HEDGE_BUDGET_EXCEEDED in result.violation_codes


def test_limits_is_only_passed_to_checks_that_accept_it() -> None:
    # price_band / liquidity / contract checks take no `limits` kwarg — the
    # aggregator must not hand it to them. A clean run over the full registry
    # exercises every check and would TypeError if it did.
    result = aggregate_risk(
        _clean_put(),
        _golden_context(),
        limits=RiskEngineLimits(
            hedge_budget=1_000_000.0, max_hedge_ratio=1.0, max_notional=1e12
        ),
    )
    assert len(result.outcomes) == 11
    assert result.passed is True


# --------------------------------------------------------------------------- #
# aggregation mechanics (explicit check list — registry-independent)
# --------------------------------------------------------------------------- #


def test_clean_plan_lists_every_check_as_pass_with_a_reason() -> None:
    result = aggregate_risk(_hypothesis(), _context(), checks=_LIMIT_CHECKS)

    assert isinstance(result, AggregateRiskResult)
    assert [c.name for c in result.checks] == _LIMIT_NAMES
    assert all(c.passed for c in result.checks)
    assert all(c.detail for c in result.checks)
    assert result.passed is True
    assert result.verdict is RiskVerdict.APPROVE
    assert result.violations == []
    assert result.violation_codes == []


def test_output_is_a_checklist_not_just_a_boolean() -> None:
    result = aggregate_risk(_hypothesis(), _context(), checks=_LIMIT_CHECKS)

    assert len(result.checks) == 4
    assert len(result.outcomes) == 4
    assert result.summary() == "4/4 deterministic risk checks passed"


def test_cycle_id_is_carried_from_the_hypothesis() -> None:
    result = aggregate_risk(
        _hypothesis(cycle_id="cyc-xyz"),
        _context(cycle_id="cyc-xyz"),
        checks=_LIMIT_CHECKS,
    )
    assert result.cycle_id == "cyc-xyz"


def test_any_hard_fail_makes_the_overall_verdict_reject() -> None:
    # budget = 0.05 * 100_000 = 5_000; a 9_000 debit is over.
    result = aggregate_risk(
        _hypothesis(cost=9_000.0), _context(), checks=_LIMIT_CHECKS
    )

    assert result.passed is False
    assert result.verdict is RiskVerdict.REJECT
    assert [c.name for c in result.checks] == _LIMIT_NAMES  # rest of list intact
    by_name = {c.name: c for c in result.checks}
    assert by_name["hedge_budget"].passed is False
    assert by_name["hedge_budget"].detail
    assert by_name["max_notional"].passed is True
    assert ViolationCode.HEDGE_BUDGET_EXCEEDED in result.violation_codes
    assert any("hedge_budget" in v for v in result.violations)


def test_every_breach_is_reported_with_its_own_code() -> None:
    ctx = _context(total_value=10_000.0, aapl_shares=100.0)
    bad = _hypothesis(
        hedge_ratio=3.0, cost=9_999.0, legs=(_leg(strike=145.0, quantity=3),)
    )

    result = aggregate_risk(bad, ctx, checks=_LIMIT_CHECKS)

    assert result.verdict is RiskVerdict.REJECT
    assert len(result.checks) == 4
    assert {c.code for c in result.failures} == {
        ViolationCode.HEDGE_BUDGET_EXCEEDED,
        ViolationCode.MAX_HEDGE_RATIO_EXCEEDED,
        ViolationCode.MAX_NOTIONAL_EXCEEDED,
        ViolationCode.POSITION_LIMIT_EXCEEDED,
    }
    assert len(result.violations) == 4


def test_a_check_returning_several_outcomes_is_flattened() -> None:
    def _limits_trio(hypothesis, context, *, limits=None):
        return run_limit_checks(hypothesis, context, limits=limits)

    result = aggregate_risk(
        _hypothesis(), _context(), checks=(check_hedge_budget, _limits_trio)
    )
    assert [c.name for c in result.checks] == _LIMIT_NAMES


def test_limits_override_threads_through_the_aggregator() -> None:
    ctx = _context(total_value=1_000_000.0, aapl_shares=100.0)
    tight = replace(RiskEngineLimits.from_context(ctx), max_notional=1_000.0)

    result = aggregate_risk(
        _hypothesis(hedge_ratio=0.5, legs=(_leg(strike=145.0, quantity=1),)),
        ctx,
        checks=_LIMIT_CHECKS,
        limits=tight,
    )

    by_name = {c.name: c for c in result.checks}
    assert by_name["max_notional"].passed is False
    assert by_name["max_hedge_ratio"].passed is True
    assert result.verdict is RiskVerdict.REJECT
    assert ViolationCode.MAX_NOTIONAL_EXCEEDED in result.violation_codes


# --------------------------------------------------------------------------- #
# soft warnings route to .warnings, they do not block
# --------------------------------------------------------------------------- #


def test_a_soft_warning_outcome_does_not_block_and_lands_in_warnings() -> None:
    def _soft(hypothesis, context):
        return CheckOutcome(
            name="soft_liquidity",
            category="OPTIONS",
            passed=True,
            warning=True,
            detail="bid/ask wide but tradeable",
        )

    result = aggregate_risk(
        _hypothesis(), _context(), checks=(check_hedge_budget, _soft)
    )

    assert result.passed is True
    assert result.verdict is RiskVerdict.APPROVE
    assert result.failures == ()
    assert result.warnings == ["soft_liquidity: bid/ask wide but tradeable"]
    assert result.summary() == "2/2 deterministic risk checks passed (1 warning)"


# --------------------------------------------------------------------------- #
# Confirm — the output shows the full checklist, not just a boolean
# --------------------------------------------------------------------------- #


def test_confirm_full_checklist_visible_on_a_reject() -> None:
    # budget = 5_000; a 50_000 debit fails only the budget check.
    result = aggregate_risk(
        _hypothesis(cost=50_000.0), _context(), checks=_LIMIT_CHECKS
    )

    assert result.verdict is RiskVerdict.REJECT
    rows = {c.name: c for c in result.checks}
    assert set(rows) == set(_LIMIT_NAMES)  # every check is on the list
    assert rows["hedge_budget"].passed is False and rows["hedge_budget"].detail
    # a specific failure, not a blanket one — the other three still pass
    assert rows["max_hedge_ratio"].passed is True
    assert rows["max_notional"].passed is True
    assert rows["position_limit"].passed is True
    assert result.summary() == "3/4 deterministic risk checks passed"
