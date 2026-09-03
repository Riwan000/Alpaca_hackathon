"""Strategy-agent base-class tests — task P4-BE-1 (BRD §15–16).

The base class gives every hedge-family agent one shape: a schema-valid
:class:`StrategyHypothesis` out of :meth:`propose`, whether the family is viable
or the agent rejects it. A :class:`SelfRejection` from ``build`` must surface as
``viable=False`` with a non-empty ``rejection_reason`` — never as an exception.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.strategies import SelfRejection, StrategyAgent
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


def _context(cycle_id: str = "cyc-p4-be-1") -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 175_000.0,
                "cash": 100_000.0,
                "equity": 75_000.0,
                "buying_power": 50_000.0,
            },
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
        }
    )


# --------------------------------------------------------------------------- #
# throwaway subclasses — the four ways build() can resolve
# --------------------------------------------------------------------------- #


class _ViablePut(StrategyAgent):
    strategy = StrategyType.PROTECTIVE_PUT

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        return self.viable(
            context,
            action=HedgeAction.NEW_HEDGE,
            cost=1_250.0,
            rationale="A 5%-OTM put floors the book within budget.",
            hedge_metrics=HedgeMetrics(hedge_ratio=0.9, cost_pct_of_portfolio=0.007),
            risks=["premium decays if spot holds"],
        )


class _RejectsViaException(StrategyAgent):
    strategy = StrategyType.PUT_SPREAD

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        raise SelfRejection("budget too small for a two-leg spread")


class _RejectsViaHelper(StrategyAgent):
    strategy = StrategyType.COLLAR

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        return self.not_viable(context, "no liquid call to finance the put")


# --------------------------------------------------------------------------- #
# viable path — Confirm: a throwaway subclass instance validates
# --------------------------------------------------------------------------- #


def test_viable_subclass_emits_a_schema_valid_hypothesis() -> None:
    hyp = _ViablePut().propose(_context())

    assert isinstance(hyp, StrategyHypothesis)
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp
    assert hyp.viable is True
    assert hyp.strategy is StrategyType.PROTECTIVE_PUT
    assert hyp.cycle_id == "cyc-p4-be-1"
    assert hyp.rejection_reason is None
    assert hyp.hedge_metrics.hedge_ratio == pytest.approx(0.9)


# --------------------------------------------------------------------------- #
# self-rejection path — NOT_VIABLE with a reason, never an exception
# --------------------------------------------------------------------------- #


def test_self_rejection_via_exception_returns_not_viable_with_a_reason() -> None:
    hyp = _RejectsViaException().propose(_context())

    assert hyp.viable is False
    assert hyp.strategy is StrategyType.PUT_SPREAD
    assert hyp.rejection_reason == "budget too small for a two-leg spread"
    assert hyp.action is HedgeAction.NO_TRADE
    StrategyHypothesis.model_validate(hyp.model_dump())


def test_self_rejection_via_helper_returns_not_viable_with_a_reason() -> None:
    hyp = _RejectsViaHelper().propose(_context())

    assert hyp.viable is False
    assert hyp.strategy is StrategyType.COLLAR
    assert hyp.rejection_reason == "no liquid call to finance the put"
    assert hyp.rationale == "no liquid call to finance the put"  # seeded from reason


def test_self_rejection_can_carry_a_non_default_action() -> None:
    class _Downsize(StrategyAgent):
        strategy = StrategyType.NO_HEDGE

        def build(self, context: HedgeContext) -> StrategyHypothesis:
            raise SelfRejection("drawdown inside tolerance", action=HedgeAction.MAINTAIN)

    hyp = _Downsize().propose(_context())
    assert hyp.viable is False
    assert hyp.action is HedgeAction.MAINTAIN


def test_a_blank_rejection_reason_is_refused() -> None:
    with pytest.raises(ValueError):
        SelfRejection("   ")


# --------------------------------------------------------------------------- #
# family / cycle invariants — a mislabelled hypothesis can't reach the manager
# --------------------------------------------------------------------------- #


def test_a_hypothesis_tagged_with_the_wrong_family_is_rejected() -> None:
    class _Mislabelled(StrategyAgent):
        strategy = StrategyType.NO_HEDGE

        def build(self, context: HedgeContext) -> StrategyHypothesis:
            return StrategyHypothesis(
                cycle_id=context.cycle_id,
                strategy=StrategyType.PROTECTIVE_PUT,  # wrong family
                action=HedgeAction.NEW_HEDGE,
                viable=True,
                cost=0.0,
                rationale="x",
            )

    with pytest.raises(ValueError, match="family"):
        _Mislabelled().propose(_context())


def test_a_hypothesis_for_a_different_cycle_is_rejected() -> None:
    class _WrongCycle(StrategyAgent):
        strategy = StrategyType.NO_HEDGE

        def build(self, context: HedgeContext) -> StrategyHypothesis:
            return self.viable(
                _context("some-other-cycle"),
                action=HedgeAction.NO_TRADE,
                cost=0.0,
                rationale="stay unhedged",
            )

    with pytest.raises(ValueError, match="cycle_id"):
        _WrongCycle().propose(_context("cyc-real"))


def test_build_must_return_a_hypothesis() -> None:
    class _ReturnsGarbage(StrategyAgent):
        strategy = StrategyType.NO_HEDGE

        def build(self, context: HedgeContext) -> StrategyHypothesis:
            return "not a hypothesis"  # type: ignore[return-value]

    with pytest.raises(TypeError):
        _ReturnsGarbage().propose(_context())


def test_a_concrete_subclass_must_declare_its_family() -> None:
    with pytest.raises(TypeError, match="StrategyType"):

        class _NoFamily(StrategyAgent):
            def build(self, context: HedgeContext) -> StrategyHypothesis:
                return self.not_viable(context, "n/a")


def test_base_class_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        StrategyAgent()  # type: ignore[abstract]
