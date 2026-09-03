"""Strategy Manager — validation stage tests — task P4-BE-7 / issue #109.

Covers the confirm scenario from the issue: four NOT_VIABLE hypotheses → the
manager short-circuits to ``NO_TRADE`` without touching the LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.strategies import StrategyManager
from backend.models.enums import DecisionType, HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_CYCLE = "cyc-p4-be-7"


def _context(*, cycle_id: str = _CYCLE, degraded: list[str] | None = None) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "degraded_sections": degraded or [],
        }
    )


def _viable(strategy: StrategyType, cycle_id: str = _CYCLE) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        cost=300.0,
        rationale="synthetic viable hypothesis",
    )


def _not_viable(strategy: StrategyType, cycle_id: str = _CYCLE) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NO_TRADE,
        viable=False,
        cost=0.0,
        rationale="no candidates",
        rejection_reason=f"{strategy.value} rejected: no candidates in chain",
    )


# --------------------------------------------------------------------------- #
# core confirm scenario (issue #109)
# --------------------------------------------------------------------------- #


def test_four_not_viable_hypotheses_yield_no_trade() -> None:
    """Confirm: feed 4 NOT_VIABLE hypotheses; decision is NO_TRADE."""
    ctx = _context()
    hypotheses = [
        _not_viable(StrategyType.PROTECTIVE_PUT),
        _not_viable(StrategyType.PUT_SPREAD),
        _not_viable(StrategyType.COLLAR),
        _not_viable(StrategyType.NO_HEDGE),
    ]

    manager = StrategyManager()
    result = manager.validate(hypotheses, ctx)

    assert result is not None, "validate() must return a StrategyDecision on all-NOT_VIABLE"
    assert result.decision is DecisionType.NO_TRADE
    assert result.selected_strategy is None
    assert result.selected_hypothesis is None
    # the rationale must mention the rejections
    assert "rejected" in result.rationale.lower() or "no viable" in result.rationale.lower()


def test_all_not_viable_rationale_includes_rejection_reasons() -> None:
    ctx = _context()
    hyps = [
        _not_viable(StrategyType.PROTECTIVE_PUT),
        _not_viable(StrategyType.COLLAR),
    ]

    result = StrategyManager().validate(hyps, ctx)

    assert result is not None
    # each rejection reason should appear in the combined rationale
    assert "PROTECTIVE_PUT" in result.rationale or "rejected" in result.rationale.lower()


# --------------------------------------------------------------------------- #
# viable path — returns None (proceed to compare/select)
# --------------------------------------------------------------------------- #


def test_at_least_one_viable_returns_none() -> None:
    ctx = _context()
    hyps = [
        _not_viable(StrategyType.PUT_SPREAD),
        _viable(StrategyType.PROTECTIVE_PUT),
        _not_viable(StrategyType.COLLAR),
    ]

    result = StrategyManager().validate(hyps, ctx)

    assert result is None, "validate() must return None when at least one hypothesis is viable"


def test_all_viable_returns_none() -> None:
    ctx = _context()
    hyps = [
        _viable(StrategyType.PROTECTIVE_PUT),
        _viable(StrategyType.NO_HEDGE),
    ]

    assert StrategyManager().validate(hyps, ctx) is None


# --------------------------------------------------------------------------- #
# empty input
# --------------------------------------------------------------------------- #


def test_empty_hypothesis_list_yields_no_trade() -> None:
    ctx = _context()

    result = StrategyManager().validate([], ctx)

    assert result is not None
    assert result.decision is DecisionType.NO_TRADE


# --------------------------------------------------------------------------- #
# malformed hypothesis — wrong cycle_id stripped
# --------------------------------------------------------------------------- #


def test_wrong_cycle_id_hypothesis_is_stripped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _context(cycle_id="cyc-A")
    stray = _viable(StrategyType.PROTECTIVE_PUT, cycle_id="cyc-B")
    legit = _not_viable(StrategyType.NO_HEDGE, cycle_id="cyc-A")

    import logging

    with caplog.at_level(logging.ERROR, logger="backend.agents.strategies.manager"):
        result = StrategyManager().validate([stray, legit], ctx)

    # stray is stripped → only legit remains → all NOT_VIABLE → NO_TRADE
    assert result is not None
    assert result.decision is DecisionType.NO_TRADE
    assert any("cycle_id" in rec.getMessage() for rec in caplog.records)


def test_all_hypotheses_wrong_cycle_id_yields_no_trade(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _context(cycle_id="cyc-A")
    stray1 = _viable(StrategyType.PROTECTIVE_PUT, cycle_id="cyc-B")
    stray2 = _viable(StrategyType.COLLAR, cycle_id="cyc-C")

    import logging

    with caplog.at_level(logging.ERROR, logger="backend.agents.strategies.manager"):
        result = StrategyManager().validate([stray1, stray2], ctx)

    assert result is not None
    assert result.decision is DecisionType.NO_TRADE


def test_mixed_cycle_ids_strips_stray_and_proceeds_with_valid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _context(cycle_id="cyc-A")
    stray = _not_viable(StrategyType.PUT_SPREAD, cycle_id="cyc-B")
    legit_viable = _viable(StrategyType.PROTECTIVE_PUT, cycle_id="cyc-A")
    legit_not_viable = _not_viable(StrategyType.COLLAR, cycle_id="cyc-A")

    import logging

    with caplog.at_level(logging.ERROR, logger="backend.agents.strategies.manager"):
        result = StrategyManager().validate([stray, legit_viable, legit_not_viable], ctx)

    # legit_viable passes → None
    assert result is None
