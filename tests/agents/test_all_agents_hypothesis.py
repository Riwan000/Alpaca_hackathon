"""Agent hypothesis validity + manager determinism suite — task P4-BE-12 / issue #114.

This file is the canonical "each agent emits a valid hypothesis; manager selection
is deterministic given fixed inputs" test suite that issue #114 requires.  It is a
*cross-cutting* integration of P4-BE-1..9 — it does not replace the individual
agent test files (``test_protective_put.py``, ``test_collar.py``, etc.), but
provides a single, self-contained suite that:

1. **Each agent emits a valid hypothesis** (viable *or* NOT_VIABLE with a
   ``rejection_reason``) that round-trips through
   :meth:`~backend.models.strategy.StrategyHypothesis.model_validate`.
2. **Manager selection is deterministic**: given the same fixed inputs, two
   consecutive calls to :meth:`~backend.agents.strategies.StrategyManager.select`
   produce the same :attr:`~backend.models.strategy.StrategyDecision.decision`,
   :attr:`~backend.models.strategy.StrategyDecision.selected_strategy`, and
   :attr:`~backend.models.strategy.StrategyDecision.rationale`.

Run with: ``pytest tests/agents -q`` (must be green — issue #114 confirm).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.agents.strategies import (
    CollarAgent,
    NoHedgeAgent,
    ProtectivePutAgent,
    PutSpreadAgent,
    StrategyManager,
    prefilter,
)
from backend.models.enums import DecisionType, HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_CYCLE = "cyc-p4-be-12"
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)

# ---------------------------------------------------------------------------
# shared context builders
# ---------------------------------------------------------------------------

_PUTS = (
    ("2026-10-03", 95.0, 3.00),
    ("2026-10-03", 90.0, 1.80),
    ("2026-10-03", 85.0, 1.00),
)
_CALLS = (
    ("2026-10-03", 110.0, 2.30),
    ("2026-10-03", 115.0, 1.40),
)


def _full_context(*, cycle_id: str = _CYCLE) -> HedgeContext:
    """HedgeContext with both put and call candidates to exercise all four agents."""
    option_candidates = [
        {
            "underlying": "XYZ",
            "right": "PUT",
            "strike": strike,
            "expiration": expiration,
            "premium": premium,
            "open_interest": 2_000,
            "iv": 0.25,
            "liquidity": "high",
        }
        for expiration, strike, premium in _PUTS
    ] + [
        {
            "underlying": "XYZ",
            "right": "CALL",
            "strike": strike,
            "expiration": expiration,
            "premium": premium,
            "open_interest": 2_000,
            "iv": 0.25,
            "liquidity": "high",
        }
        for expiration, strike, premium in _CALLS
    ]
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [
                    {
                        "symbol": "XYZ",
                        "qty": 100.0,
                        "avg_price": 80.0,
                        "market_value": 10_000.0,
                    }
                ],
                "drawdown": -0.046,
                "volatility": 0.28,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": option_candidates,
        }
    )


def _viable_hypothesis(
    strategy: StrategyType,
    *,
    cost: float = 300.0,
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    """Minimal viable hypothesis for manager tests."""
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=(
            HedgeAction.NEW_HEDGE
            if strategy is not StrategyType.NO_HEDGE
            else HedgeAction.NO_TRADE
        ),
        viable=True,
        cost=cost,
        rationale=f"synthetic viable {strategy.value}",
        hedge_metrics=HedgeMetrics(
            downside_protection_pct=0.08 if strategy is not StrategyType.NO_HEDGE else 0.0,
            cost_pct_of_portfolio=cost / 100_000,
        ),
    )


def _manager_context(*, degraded: list[str] | None = None) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
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


def _llm_response(
    *,
    decision: str = "SELECT_STRATEGY",
    selected_strategy: str | None = "PROTECTIVE_PUT",
    rationale: str = "Protective put offers the best floor for the cost.",
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


# ===========================================================================
# Section 1 — Each agent emits a schema-valid hypothesis (P4-BE-2..5)
# ===========================================================================


class TestEachAgentEmitsAValidHypothesis:
    """Every agent's ``propose()`` output must round-trip through Pydantic.

    These tests run agents against a shared context that contains both put and
    call candidates, so every agent has enough data to produce a viable result.
    NOT_VIABLE outcomes (when context omits required candidates) are tested
    separately as the ``_not_viable_*`` cases.
    """

    def _assert_valid(self, hyp: StrategyHypothesis) -> None:
        assert isinstance(hyp, StrategyHypothesis)
        StrategyHypothesis.model_validate(hyp.model_dump())
        if not hyp.viable:
            assert hyp.rejection_reason and hyp.rejection_reason.strip(), (
                "NOT_VIABLE hypothesis must carry a rejection_reason"
            )

    # ---- ProtectivePutAgent ------------------------------------------------

    def test_protective_put_emits_valid_viable_hypothesis(self) -> None:
        ctx = _full_context()
        hyp = ProtectivePutAgent().propose(ctx)

        self._assert_valid(hyp)
        assert hyp.strategy is StrategyType.PROTECTIVE_PUT
        assert hyp.viable is True
        assert hyp.cost > 0

    def test_protective_put_not_viable_on_empty_book(self) -> None:
        ctx = _full_context()
        bare = ctx.model_copy(
            update={
                "portfolio_state": ctx.portfolio_state.model_copy(update={"positions": []})
            }
        )
        hyp = ProtectivePutAgent().propose(bare)

        self._assert_valid(hyp)
        assert hyp.viable is False
        assert hyp.strategy is StrategyType.PROTECTIVE_PUT

    # ---- PutSpreadAgent ----------------------------------------------------

    def test_put_spread_emits_valid_viable_hypothesis(self) -> None:
        ctx = _full_context()
        hyp = PutSpreadAgent().propose(ctx)

        self._assert_valid(hyp)
        assert hyp.strategy is StrategyType.PUT_SPREAD
        assert hyp.viable is True
        # long leg above short leg
        if len(hyp.legs) == 2:
            long_leg = next(
                (leg for leg in hyp.legs if leg.side.value == "BUY"), None
            )
            short_leg = next(
                (leg for leg in hyp.legs if leg.side.value == "SELL"), None
            )
            if long_leg and short_leg:
                assert long_leg.strike > short_leg.strike

    def test_put_spread_not_viable_with_only_one_strike(self) -> None:
        ctx = _full_context()
        # Replace candidates with only a single put strike
        single_put = ctx.model_copy(
            update={
                "option_candidates": [
                    cand
                    for cand in ctx.option_candidates
                    if cand.right.value == "PUT" and cand.strike == 95.0
                ]
            }
        )
        hyp = PutSpreadAgent().propose(single_put)

        self._assert_valid(hyp)
        assert hyp.viable is False
        assert hyp.strategy is StrategyType.PUT_SPREAD

    # ---- CollarAgent -------------------------------------------------------

    def test_collar_emits_valid_viable_hypothesis(self) -> None:
        ctx = _full_context()
        hyp = CollarAgent().propose(ctx)

        self._assert_valid(hyp)
        assert hyp.strategy is StrategyType.COLLAR
        assert hyp.viable is True
        assert len(hyp.legs) == 2

    def test_collar_not_viable_without_calls(self) -> None:
        ctx = _full_context()
        puts_only = ctx.model_copy(
            update={
                "option_candidates": [
                    c for c in ctx.option_candidates if c.right.value == "PUT"
                ]
            }
        )
        hyp = CollarAgent().propose(puts_only)

        self._assert_valid(hyp)
        assert hyp.viable is False
        assert hyp.strategy is StrategyType.COLLAR

    # ---- NoHedgeAgent ------------------------------------------------------

    def test_no_hedge_always_emits_a_viable_hypothesis(self) -> None:
        ctx = _full_context()
        hyp = NoHedgeAgent().propose(ctx)

        self._assert_valid(hyp)
        assert hyp.strategy is StrategyType.NO_HEDGE
        assert hyp.viable is True
        assert hyp.cost == 0.0
        assert hyp.action is HedgeAction.NO_TRADE

    def test_no_hedge_viable_even_on_minimal_context(self) -> None:
        minimal = HedgeContext.model_validate(
            {
                "cycle_id": _CYCLE,
                "timestamp": _NOW.isoformat(),
                "portfolio_state": {
                    "total_value": 50_000.0,
                    "cash": 50_000.0,
                    "equity": 0.0,
                    "buying_power": 50_000.0,
                },
                "objective": {
                    "max_hedge_budget_pct": 0.05,
                    "drawdown_tolerance_pct": 0.10,
                },
            }
        )
        hyp = NoHedgeAgent().propose(minimal)
        self._assert_valid(hyp)
        assert hyp.viable is True

    # ---- Golden context — all four agents ----------------------------------

    def test_all_four_agents_on_golden_context_emit_valid_hypotheses(self) -> None:
        """Smoke test: run all four agents on the recorded golden fixture."""
        ctx = HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))
        agents = [
            ProtectivePutAgent(),
            PutSpreadAgent(),
            CollarAgent(),
            NoHedgeAgent(),
        ]
        strategy_types_seen: set[StrategyType] = set()
        for agent in agents:
            hyp = agent.propose(ctx)
            self._assert_valid(hyp)
            strategy_types_seen.add(hyp.strategy)

        # All four families must be represented
        assert strategy_types_seen == {
            StrategyType.PROTECTIVE_PUT,
            StrategyType.PUT_SPREAD,
            StrategyType.COLLAR,
            StrategyType.NO_HEDGE,
        }


# ===========================================================================
# Section 2 — Manager selection is deterministic given fixed inputs (P4-BE-9)
# ===========================================================================


class TestManagerSelectionIsDeterministic:
    """``StrategyManager.select`` must produce identical output for identical inputs.

    This is the issue #114 confirm: *manager selection is deterministic given fixed
    inputs*.  Two back-to-back calls with the same ``viable``, ``comparison``,
    ``not_viable``, and ``context`` must yield the same ``decision``,
    ``selected_strategy``, and ``rationale``.
    """

    def _select_twice(
        self,
        viable: list[StrategyHypothesis],
        not_viable: list[StrategyHypothesis],
        mock_llm: Any,
        *,
        degraded: list[str] | None = None,
    ) -> tuple[Any, Any]:
        ctx = _manager_context(degraded=degraded)
        comparison = StrategyManager().compare(viable, ctx)
        manager = StrategyManager(client=mock_llm)
        r1 = manager.select(viable, comparison, not_viable, ctx)
        r2 = manager.select(viable, comparison, not_viable, ctx)
        return r1, r2

    def _assert_same(self, r1: Any, r2: Any) -> None:
        assert r1.decision is r2.decision
        assert r1.selected_strategy is r2.selected_strategy
        assert r1.rationale == r2.rationale

    def test_select_strategy_is_deterministic(self, mock_llm: Any) -> None:
        viable = [
            _viable_hypothesis(StrategyType.PROTECTIVE_PUT, cost=315.0),
            _viable_hypothesis(StrategyType.NO_HEDGE, cost=0.0),
        ]
        mock_llm.response_content = _llm_response(selected_strategy="PROTECTIVE_PUT")
        r1, r2 = self._select_twice(viable, [], mock_llm)
        self._assert_same(r1, r2)
        assert r1.decision is DecisionType.SELECT_STRATEGY

    def test_no_trade_is_deterministic(self, mock_llm: Any) -> None:
        viable = [
            _viable_hypothesis(StrategyType.PROTECTIVE_PUT, cost=315.0),
        ]
        mock_llm.response_content = _llm_response(
            decision="NO_TRADE",
            selected_strategy=None,
            rationale="Cost of hedging outweighs benefit.",
        )
        r1, r2 = self._select_twice(viable, [], mock_llm)
        self._assert_same(r1, r2)
        assert r1.decision is DecisionType.NO_TRADE

    def test_reassess_is_deterministic_on_degraded_context(self, mock_llm: Any) -> None:
        viable = [_viable_hypothesis(StrategyType.PROTECTIVE_PUT, cost=315.0)]
        mock_llm.response_content = _llm_response(
            decision="SELECT_STRATEGY",
            selected_strategy="PROTECTIVE_PUT",
            confidence=0.9,
        )
        r1, r2 = self._select_twice(
            viable, [], mock_llm, degraded=["market_state"]
        )
        self._assert_same(r1, r2)
        assert r1.decision is DecisionType.REASSESS

    def test_deterministic_fallback_is_deterministic(self, mock_llm: Any) -> None:
        """When the LLM fails, the lowest-cost selection is still deterministic."""
        viable = [
            _viable_hypothesis(StrategyType.PUT_SPREAD, cost=120.0),
            _viable_hypothesis(StrategyType.PROTECTIVE_PUT, cost=315.0),
            _viable_hypothesis(StrategyType.NO_HEDGE, cost=0.0),
        ]
        mock_llm.response_content = "not valid json"  # force deterministic fallback
        r1, r2 = self._select_twice(viable, [], mock_llm)
        self._assert_same(r1, r2)
        # Fallback selects lowest-cost non-NO_HEDGE → PUT_SPREAD at 120
        assert r1.selected_strategy is StrategyType.PUT_SPREAD

    def test_run_pipeline_is_deterministic_on_golden_context(self, mock_llm: Any) -> None:
        """Full manager.run() on the golden context is deterministic end-to-end."""
        ctx = HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))
        agents = [ProtectivePutAgent(), PutSpreadAgent(), CollarAgent(), NoHedgeAgent()]
        hypotheses = [a.propose(ctx) for a in agents]
        pre_result = prefilter(hypotheses, ctx)

        mock_llm.response_content = _llm_response(
            selected_strategy="PROTECTIVE_PUT",
            rationale="Protective put floors the position within the drawdown tolerance.",
            confidence=0.88,
        )

        manager = StrategyManager(client=mock_llm)
        d1 = manager.run(pre_result, ctx)
        d2 = manager.run(pre_result, ctx)

        assert d1.decision is d2.decision
        assert d1.selected_strategy is d2.selected_strategy
        assert d1.rationale == d2.rationale
        assert d1.cycle_id == ctx.cycle_id

        # Schema-validity
        StrategyHypothesis  # re-exported for clarity
        from backend.models.strategy import StrategyDecision

        StrategyDecision.model_validate(d1.model_dump())


# ===========================================================================
# Section 3 — Prefilter + full pipeline integration (P4-BE-6)
# ===========================================================================


class TestFullPipelineIntegration:
    """Four agents → prefilter → StrategyManager.run() integration."""

    def test_pipeline_yields_schema_valid_decision(self, mock_llm: Any) -> None:
        """The full pipeline output must round-trip through StrategyDecision."""
        ctx = _full_context()
        agents = [ProtectivePutAgent(), PutSpreadAgent(), CollarAgent(), NoHedgeAgent()]
        hypotheses = [a.propose(ctx) for a in agents]
        pre_result = prefilter(hypotheses, ctx)

        mock_llm.response_content = _llm_response(selected_strategy="PROTECTIVE_PUT")
        decision = StrategyManager(client=mock_llm).run(pre_result, ctx)

        from backend.models.strategy import StrategyDecision

        StrategyDecision.model_validate(decision.model_dump())
        assert decision.cycle_id == ctx.cycle_id
        assert decision.decision in DecisionType

    def test_all_hypotheses_present_in_decision_alternatives(self, mock_llm: Any) -> None:
        """The manager must carry dropped hypotheses into the decision.alternatives."""
        ctx = _full_context()
        agents = [ProtectivePutAgent(), PutSpreadAgent(), CollarAgent(), NoHedgeAgent()]
        hypotheses = [a.propose(ctx) for a in agents]
        pre_result = prefilter(hypotheses, ctx)

        mock_llm.response_content = _llm_response(selected_strategy="PROTECTIVE_PUT")
        decision = StrategyManager(client=mock_llm).run(pre_result, ctx)

        # All hypotheses that weren't selected end up in alternatives
        all_strategies = {h.strategy for h in hypotheses}
        accounted = set()
        if decision.selected_strategy:
            accounted.add(decision.selected_strategy)
        for alt in decision.alternatives:
            accounted.add(alt.strategy)
        assert accounted == all_strategies
