"""Deterministic pre-filter tests — task P4-BE-6 (BRD §17).

The pre-filter sits between the strategy agents and the LLM Strategy Manager: a
viable hypothesis that blows the hedge budget, over-hedges past the ratio ceiling
or controls more notional than the book is worth is dropped here, with a logged
reason, so the manager never reasons about it. NOT_VIABLE families pass straight
through. The final case forces an over-budget proposal out of a *real* agent and
confirms it never reaches ``kept`` and lands in the log.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.agents.strategies import (
    NoHedgeAgent,
    PrefilterLimits,
    ProtectivePutAgent,
    prefilter,
)
from backend.agents.strategies.prefilter import (
    DEFAULT_MAX_HEDGE_RATIO,
    hypothesis_notional,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_PREFILTER_LOGGER = "backend.agents.strategies.prefilter"
_CYCLE = "cyc-p4-be-6"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)


def _context(
    *,
    total_value: float = 100_000.0,
    budget_pct: float = 0.05,
    target_hedge_ratio: float | None = None,
    cycle_id: str = _CYCLE,
) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": total_value / 4,
            },
            "objective": {
                "max_hedge_budget_pct": budget_pct,
                "drawdown_tolerance_pct": 0.10,
                "target_hedge_ratio": target_hedge_ratio,
            },
        }
    )


def _leg(*, strike: float = 145.0, quantity: int = 1) -> OptionLeg:
    return OptionLeg(
        underlying="AAPL",
        right=OptionRight.PUT,
        side=OrderSide.BUY,
        strike=strike,
        expiration=date(2026, 10, 3),
        quantity=quantity,
    )


def _viable(
    *,
    strategy: StrategyType = StrategyType.PROTECTIVE_PUT,
    cost: float = 250.0,
    hedge_ratio: float | None = 0.8,
    legs: tuple[OptionLeg, ...] = (_leg(),),
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=hedge_ratio),
        rationale="synthetic viable hypothesis for the pre-filter tests",
    )


def _not_viable(
    *, strategy: StrategyType = StrategyType.COLLAR, cycle_id: str = _CYCLE
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NO_TRADE,
        viable=False,
        cost=0.0,
        rationale="family rejected",
        rejection_reason="no call candidates to finance a collar",
    )


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #


def test_over_budget_viable_hypothesis_is_dropped_with_a_logged_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # budget = 0.05 * 100_000 = 5_000; a 6_000 debit is over.
    ctx = _context()
    over = _viable(cost=6_000.0)

    with caplog.at_level(logging.WARNING, logger=_PREFILTER_LOGGER):
        result = prefilter([over], ctx)

    assert result.kept == ()
    assert result.dropped_strategies == (StrategyType.PROTECTIVE_PUT,)
    reason = " ".join(result.reasons_for(StrategyType.PROTECTIVE_PUT)).lower()
    assert "budget" in reason or "cost" in reason
    assert any(
        rec.levelno == logging.WARNING
        and "pre-filter dropped PROTECTIVE_PUT" in rec.getMessage()
        for rec in caplog.records
    )


def test_at_budget_exactly_is_kept() -> None:
    ctx = _context()
    at_limit = _viable(cost=5_000.0, hedge_ratio=0.5, legs=(_leg(quantity=1),))

    result = prefilter([at_limit], ctx)

    assert result.dropped == ()
    assert result.kept_strategies == (StrategyType.PROTECTIVE_PUT,)


# --------------------------------------------------------------------------- #
# hedge ratio
# --------------------------------------------------------------------------- #


def test_over_max_hedge_ratio_is_dropped() -> None:
    # no target on the objective → ceiling is DEFAULT_MAX_HEDGE_RATIO (1.0)
    ctx = _context()
    over = _viable(cost=100.0, hedge_ratio=1.5)

    result = prefilter([over], ctx)

    assert result.was_dropped(StrategyType.PROTECTIVE_PUT)
    assert "hedge ratio" in " ".join(
        result.reasons_for(StrategyType.PROTECTIVE_PUT)
    )


def test_objective_target_raises_the_hedge_ratio_ceiling() -> None:
    # target 1.6 → a 1.5 ratio is now within policy
    ctx = _context(target_hedge_ratio=1.6)
    hyp = _viable(cost=100.0, hedge_ratio=1.5)

    result = prefilter([hyp], ctx)

    assert result.kept_strategies == (StrategyType.PROTECTIVE_PUT,)


def test_missing_hedge_ratio_is_treated_as_zero() -> None:
    ctx = _context()
    hyp = _viable(cost=100.0, hedge_ratio=None)

    result = prefilter([hyp], ctx)

    assert result.dropped == ()


# --------------------------------------------------------------------------- #
# notional
# --------------------------------------------------------------------------- #


def test_over_notional_is_dropped() -> None:
    # tiny book (total_value 10_000); one 145 put contract controls
    # 145 * 100 = 14_500 of notional — over the book's value.
    ctx = _context(total_value=10_000.0)
    over = _viable(cost=100.0, hedge_ratio=0.1, legs=(_leg(strike=145.0),))

    result = prefilter([over], ctx)

    assert result.was_dropped(StrategyType.PROTECTIVE_PUT)
    assert "notional" in " ".join(
        result.reasons_for(StrategyType.PROTECTIVE_PUT)
    )


def test_hypothesis_notional_sums_leg_magnitudes() -> None:
    hyp = _viable(legs=(_leg(strike=145.0, quantity=1), _leg(strike=140.0, quantity=1)))
    # (145 + 140) * 100
    assert hypothesis_notional(hyp) == pytest.approx(28_500.0)


def test_no_leg_hypothesis_has_zero_notional() -> None:
    assert hypothesis_notional(_viable(legs=())) == 0.0


# --------------------------------------------------------------------------- #
# multiple violations / pass-through / ordering
# --------------------------------------------------------------------------- #


def test_every_breached_limit_is_reported() -> None:
    ctx = _context(total_value=10_000.0)  # budget 500, notional cap 10_000
    bad = _viable(cost=9_000.0, hedge_ratio=3.0, legs=(_leg(strike=145.0, quantity=2),))

    result = prefilter([bad], ctx)

    reasons = result.reasons_for(StrategyType.PROTECTIVE_PUT)
    assert len(reasons) == 3
    joined = " ".join(reasons).lower()
    assert "hedge ratio" in joined
    assert "notional" in joined
    assert "budget" in joined or "cost" in joined


def test_not_viable_hypotheses_pass_through_untouched() -> None:
    ctx = _context(budget_pct=0.001)  # budget 100 — brutally tight
    rejected = _not_viable()

    result = prefilter([rejected], ctx)

    assert result.dropped == ()
    assert result.kept == (rejected,)


def test_kept_preserves_input_order_and_drops_only_the_breacher() -> None:
    ctx = _context()
    keep_a = _viable(strategy=StrategyType.PROTECTIVE_PUT, cost=200.0, hedge_ratio=0.9)
    drop = _viable(strategy=StrategyType.PUT_SPREAD, cost=99_000.0, hedge_ratio=0.5)
    keep_b = _viable(strategy=StrategyType.NO_HEDGE, cost=0.0, hedge_ratio=0.0, legs=())

    result = prefilter([keep_a, drop, keep_b], ctx)

    assert result.kept_strategies == (
        StrategyType.PROTECTIVE_PUT,
        StrategyType.NO_HEDGE,
    )
    assert result.dropped_strategies == (StrategyType.PUT_SPREAD,)


def test_custom_limits_override_the_context_defaults() -> None:
    ctx = _context()  # context budget would be 5_000
    hyp = _viable(cost=4_000.0, hedge_ratio=0.5)
    tight = replace(PrefilterLimits.from_context(ctx), budget=1_000.0)

    result = prefilter([hyp], ctx, limits=tight)

    assert result.was_dropped(StrategyType.PROTECTIVE_PUT)


def test_empty_input_is_an_empty_result() -> None:
    result = prefilter([], _context())

    assert result.kept == ()
    assert result.dropped == ()


def test_cycle_id_mismatch_raises() -> None:
    ctx = _context(cycle_id="cyc-A")
    stray = _viable(cycle_id="cyc-B")

    with pytest.raises(ValueError, match="cycle_id"):
        prefilter([stray], ctx)


def test_default_ceiling_constant_is_one() -> None:
    assert DEFAULT_MAX_HEDGE_RATIO == 1.0


# --------------------------------------------------------------------------- #
# Confirm — a real agent's over-budget proposal never reaches the manager
# --------------------------------------------------------------------------- #


def _golden_context() -> HedgeContext:
    return HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))


def test_confirm_forced_over_budget_agent_output_never_reaches_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _golden_context()
    agents = (ProtectivePutAgent(), NoHedgeAgent())
    hypotheses = [agent.propose(ctx) for agent in agents]

    # The protective put is genuinely viable on the seed context (~$315).
    put = next(h for h in hypotheses if h.strategy is StrategyType.PROTECTIVE_PUT)
    assert put.viable is True

    # Force it over budget: drop the hedge budget to $100.
    starved = replace(PrefilterLimits.from_context(ctx), budget=100.0)

    with caplog.at_level(logging.WARNING, logger=_PREFILTER_LOGGER):
        result = prefilter(hypotheses, ctx, limits=starved)

    # It is gone from what the manager sees, with a logged budget reason...
    assert StrategyType.PROTECTIVE_PUT not in result.kept_strategies
    assert result.was_dropped(StrategyType.PROTECTIVE_PUT)
    assert "budget" in " ".join(
        result.reasons_for(StrategyType.PROTECTIVE_PUT)
    ).lower()
    assert any(
        "pre-filter dropped PROTECTIVE_PUT" in rec.getMessage()
        and str(ctx.cycle_id) in rec.getMessage()
        for rec in caplog.records
    )
    # ...while the zero-cost No-Hedge alternative still reaches the manager.
    assert StrategyType.NO_HEDGE in result.kept_strategies


def test_confirm_within_limits_all_agent_output_passes_through() -> None:
    ctx = _golden_context()
    agents = (ProtectivePutAgent(), NoHedgeAgent())
    hypotheses = [agent.propose(ctx) for agent in agents]

    result = prefilter(hypotheses, ctx)

    assert result.dropped == ()
    assert set(result.kept_strategies) == {
        StrategyType.PROTECTIVE_PUT,
        StrategyType.NO_HEDGE,
    }
