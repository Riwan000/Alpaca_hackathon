"""Strategy Manager — selection stage tests — task P4-BE-9 / issue #111.

Covers:
  - Deterministic output on fixed inputs (same input twice → same decision).
  - Selected hypothesis is cited in rationale.
  - Degraded context → REASSESS.
  - LLM parse failure → deterministic fallback.
  - Low-confidence LLM signal → REASSESS.
  - All-NO_HEDGE viable → NO_TRADE fallback.

Uses the ``mock_llm`` fixture from ``tests/conftest.py`` (no real network call).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.agents.strategies import StrategyManager
from backend.models.enums import DecisionType, HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import ComparisonRow, HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_CYCLE = "cyc-p4-be-9"


def _context(
    *,
    cycle_id: str = _CYCLE,
    degraded: list[str] | None = None,
    total_value: float = 100_000.0,
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
                "drawdown": -0.046,
                "volatility": 0.18,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "degraded_sections": degraded or [],
        }
    )


def _viable(
    strategy: StrategyType,
    *,
    cost: float = 300.0,
    cycle_id: str = _CYCLE,
    rejection_conditions: list[str] | None = None,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE if strategy is not StrategyType.NO_HEDGE else HedgeAction.NO_TRADE,
        viable=True,
        cost=cost,
        rationale=f"synthetic viable {strategy.value} at cost ${cost:,.0f}",
        hedge_metrics=HedgeMetrics(
            hedge_ratio=0.85 if strategy is not StrategyType.NO_HEDGE else 0.0,
            downside_protection_pct=0.08 if strategy is not StrategyType.NO_HEDGE else 0.0,
            cost_pct_of_portfolio=cost / 100_000,
        ),
        rejection_conditions=rejection_conditions or [],
    )


def _comparison(viable: list[StrategyHypothesis]) -> list[ComparisonRow]:
    return StrategyManager().compare(viable, _context())


def _llm_response(
    *,
    decision: str = "SELECT_STRATEGY",
    selected_strategy: str | None = "PROTECTIVE_PUT",
    rationale: str = "Protective put offers the best downside protection for the cost.",
    confidence: float = 0.9,
) -> str:
    return json.dumps(
        {
            "decision": decision,
            "selected_strategy": selected_strategy,
            "rationale": rationale,
            "confidence": confidence,
        }
    )


# --------------------------------------------------------------------------- #
# deterministic selection (issue #111 confirm: same input twice → same decision)
# --------------------------------------------------------------------------- #


def test_same_input_twice_yields_same_decision(mock_llm: Any) -> None:
    """Confirm: same input twice → same decision + rationale."""
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(selected_strategy="PROTECTIVE_PUT")

    manager = StrategyManager(client=mock_llm)
    result1 = manager.select(viable, comparison, [], ctx)
    result2 = manager.select(viable, comparison, [], ctx)

    assert result1.decision is result2.decision
    assert result1.selected_strategy is result2.selected_strategy
    assert result1.rationale == result2.rationale


def test_selected_hypothesis_is_cited_in_decision(mock_llm: Any) -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        selected_strategy="PROTECTIVE_PUT",
        rationale="Protective put offers downside protection within budget.",
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.SELECT_STRATEGY
    assert result.selected_strategy is StrategyType.PROTECTIVE_PUT
    assert result.selected_hypothesis is not None
    assert result.selected_hypothesis.strategy is StrategyType.PROTECTIVE_PUT
    assert "protective put" in result.rationale.lower() or "PROTECTIVE_PUT" in result.rationale


def test_selected_strategy_matches_selected_hypothesis(mock_llm: Any) -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PUT_SPREAD, cost=120.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        selected_strategy="PUT_SPREAD",
        rationale="Put spread is the most cost-efficient hedge.",
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.selected_strategy is StrategyType.PUT_SPREAD
    assert result.selected_hypothesis is not None
    assert result.selected_hypothesis.strategy is result.selected_strategy


# --------------------------------------------------------------------------- #
# degraded context → REASSESS
# --------------------------------------------------------------------------- #


def test_degraded_context_yields_reassess(mock_llm: Any) -> None:
    ctx = _context(degraded=["market_state", "news_context"])
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="SELECT_STRATEGY",
        selected_strategy="PROTECTIVE_PUT",
        confidence=0.9,
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.REASSESS
    assert "degraded" in result.rationale.lower()
    assert any("market_state" in c or "news_context" in c for c in result.reassessment_conditions)


# --------------------------------------------------------------------------- #
# LLM parse failure → deterministic fallback
# --------------------------------------------------------------------------- #


def test_unparsable_llm_response_triggers_deterministic_fallback(mock_llm: Any) -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.PUT_SPREAD, cost=120.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = "Sorry, I cannot make that decision right now."

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    # fallback selects lowest-cost non-NO_HEDGE
    assert result.decision is DecisionType.SELECT_STRATEGY
    assert result.selected_strategy is StrategyType.PUT_SPREAD  # cost 120 < 315


def test_invalid_json_triggers_deterministic_fallback(mock_llm: Any) -> None:
    ctx = _context()
    viable = [_viable(StrategyType.PROTECTIVE_PUT, cost=315.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = "{not valid json"

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.SELECT_STRATEGY
    assert result.selected_strategy is StrategyType.PROTECTIVE_PUT


# --------------------------------------------------------------------------- #
# low-confidence → REASSESS
# --------------------------------------------------------------------------- #


def test_low_confidence_llm_response_yields_reassess(mock_llm: Any) -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="SELECT_STRATEGY",
        selected_strategy="PROTECTIVE_PUT",
        confidence=0.3,  # below the 0.5 threshold
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.REASSESS
    assert "30%" in result.rationale or "confidence" in result.rationale.lower()


def test_confidence_exactly_at_threshold_is_accepted(mock_llm: Any) -> None:
    ctx = _context()
    viable = [_viable(StrategyType.PROTECTIVE_PUT, cost=315.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        confidence=0.5,  # exactly at threshold — should be accepted
        selected_strategy="PROTECTIVE_PUT",
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    # 0.5 is not < 0.5 so should not trigger REASSESS on confidence alone
    assert result.decision is not DecisionType.REASSESS or "degraded" in result.rationale.lower()


# --------------------------------------------------------------------------- #
# LLM explicit REASSESS and NO_TRADE
# --------------------------------------------------------------------------- #


def test_llm_reassess_decision_is_forwarded(mock_llm: Any) -> None:
    ctx = _context()
    viable = [_viable(StrategyType.PROTECTIVE_PUT, cost=315.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="REASSESS",
        selected_strategy=None,
        rationale="Market conditions are too uncertain.",
        confidence=0.8,
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.REASSESS


def test_llm_no_trade_decision_is_forwarded(mock_llm: Any) -> None:
    ctx = _context()
    viable = [_viable(StrategyType.PROTECTIVE_PUT, cost=315.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="NO_TRADE",
        selected_strategy=None,
        rationale="Cost of hedging outweighs the benefit.",
        confidence=0.8,
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.NO_TRADE
    assert result.selected_strategy is None


# --------------------------------------------------------------------------- #
# fallback: all viable are NO_HEDGE → NO_TRADE
# --------------------------------------------------------------------------- #


def test_all_viable_no_hedge_falls_back_to_no_trade_on_parse_error(mock_llm: Any) -> None:
    ctx = _context()
    viable = [_viable(StrategyType.NO_HEDGE, cost=0.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = "not json"  # force fallback

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.NO_TRADE


# --------------------------------------------------------------------------- #
# LLM returns unknown strategy → fallback
# --------------------------------------------------------------------------- #


def test_llm_unknown_strategy_name_triggers_fallback(mock_llm: Any) -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="SELECT_STRATEGY",
        selected_strategy="SUPER_HEDGE",  # not a valid StrategyType
        confidence=0.9,
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    # should fall back; the fallback selects lowest-cost non-NO_HEDGE
    assert result.decision is DecisionType.SELECT_STRATEGY
    assert result.selected_strategy is StrategyType.PROTECTIVE_PUT


def test_llm_selects_strategy_not_in_viable_set_triggers_fallback(mock_llm: Any) -> None:
    ctx = _context()
    # only PUT_SPREAD is in the viable set
    viable = [_viable(StrategyType.PUT_SPREAD, cost=120.0)]
    comparison = _comparison(viable)
    mock_llm.response_content = _llm_response(
        decision="SELECT_STRATEGY",
        selected_strategy="PROTECTIVE_PUT",  # not in the viable set
        confidence=0.9,
    )

    result = StrategyManager(client=mock_llm).select(viable, comparison, [], ctx)

    assert result.decision is DecisionType.SELECT_STRATEGY
    assert result.selected_strategy is StrategyType.PUT_SPREAD


# --------------------------------------------------------------------------- #
# run() integration (chains all three stages)
# --------------------------------------------------------------------------- #


def test_run_chains_validate_compare_select(mock_llm: Any) -> None:
    """Test the full manager.run() pipeline with a mock LLM."""
    from backend.agents.strategies import prefilter, ProtectivePutAgent, NoHedgeAgent
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "analyze"
        / "hedge_context_golden.json"
    )
    if not golden_path.exists():
        pytest.skip("golden fixture not available")

    ctx = HedgeContext.model_validate(json.loads(golden_path.read_text("utf-8")))
    agents = [ProtectivePutAgent(), NoHedgeAgent()]
    hypotheses = [a.propose(ctx) for a in agents]
    pre_result = prefilter(hypotheses, ctx)

    mock_llm.response_content = _llm_response(
        selected_strategy="PROTECTIVE_PUT",
        rationale="Protective put is the best choice given current drawdown.",
        confidence=0.85,
    )

    manager = StrategyManager(client=mock_llm)
    decision = manager.run(pre_result, ctx)

    assert decision.cycle_id == ctx.cycle_id
    assert decision.decision in (
        DecisionType.SELECT_STRATEGY,
        DecisionType.NO_TRADE,
        DecisionType.REASSESS,
    )
    from backend.models.strategy import StrategyDecision
    StrategyDecision.model_validate(decision.model_dump())
