"""Strategy-agent interface + base class — task P4-BE-1 (BRD §15–16).

Phase 4 runs four **strategy agents** — one per hedge family (protective put,
put spread, collar, no-hedge). Each consumes the assembled
:class:`~backend.models.hedge_context.HedgeContext` and emits exactly one
:class:`~backend.models.strategy.StrategyHypothesis`: its best proposal for that
family, *or* a first-class rejection of the family for this context
(``viable=False`` with a ``rejection_reason`` — BRD §16, never an exception the
Strategy Manager has to interpret).

:class:`StrategyAgent` is that common shape. A concrete agent sets the
``strategy`` class attribute and implements :meth:`build`; callers only ever use
:meth:`propose`, which

* returns the subclass's hypothesis unchanged when it is viable;
* converts a :class:`SelfRejection` raised anywhere inside ``build`` into a
  schema-valid NOT_VIABLE hypothesis carrying the reason;
* guards the family / cycle invariants so a mislabelled hypothesis can't reach
  the manager.

The helpers :meth:`viable` / :meth:`not_viable` fill the fields every family
shares (``cycle_id`` from the context, ``strategy`` from the class) so
P4-BE-2..5 stay focused on the quant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, PayoffPoint, StrategyHypothesis

__all__ = ["SelfRejection", "StrategyAgent"]


class SelfRejection(Exception):
    """A strategy agent has rejected its own family for the current context.

    Raise it from anywhere inside :meth:`StrategyAgent.build` to abandon the
    proposal without assembling a full hypothesis;
    :meth:`StrategyAgent.propose` turns it into a NOT_VIABLE
    :class:`~backend.models.strategy.StrategyHypothesis` whose
    ``rejection_reason`` is ``reason``. This is an expected outcome (BRD §16),
    not an error path.
    """

    def __init__(
        self, reason: str, *, action: HedgeAction = HedgeAction.NO_TRADE
    ) -> None:
        if not reason or not reason.strip():
            raise ValueError("SelfRejection needs a non-empty reason")
        super().__init__(reason)
        self.reason = reason
        self.action = action


class StrategyAgent(ABC):
    """Base class for the four Phase-4 strategy agents (BRD §15–16).

    Subclasses set :attr:`strategy` and implement :meth:`build`; the
    viable / not-viable bookkeeping and the family invariants live here.
    """

    #: The hedge family this agent proposes for. Every concrete subclass sets it.
    strategy: ClassVar[StrategyType]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return  # still abstract — a concrete agent below it gets checked
        if not isinstance(getattr(cls, "strategy", None), StrategyType):
            raise TypeError(
                f"{cls.__name__} must set `strategy` to a StrategyType member"
            )

    # ------------------------------------------------------------------ #
    # public entrypoint
    # ------------------------------------------------------------------ #

    def propose(self, context: HedgeContext) -> StrategyHypothesis:
        """This agent's single hypothesis for ``context`` — viable or not.

        Never raises for a rejected family: a :class:`SelfRejection` from
        :meth:`build` comes back as a NOT_VIABLE hypothesis with the reason.
        A ``build`` that returns the wrong type or a hypothesis tagged with a
        different family / cycle is a programming error and does raise.
        """
        try:
            hypothesis = self.build(context)
        except SelfRejection as rejection:
            return self.not_viable(
                context, rejection.reason, action=rejection.action
            )

        if not isinstance(hypothesis, StrategyHypothesis):
            raise TypeError(
                f"{type(self).__name__}.build must return a StrategyHypothesis, "
                f"got {type(hypothesis).__name__}"
            )
        if hypothesis.strategy is not self.strategy:
            raise ValueError(
                f"{type(self).__name__} proposed a {hypothesis.strategy.value} "
                f"hypothesis for the {self.strategy.value} family"
            )
        if hypothesis.cycle_id != context.cycle_id:
            raise ValueError(
                f"hypothesis cycle_id {hypothesis.cycle_id!r} != context "
                f"{context.cycle_id!r}"
            )
        return hypothesis

    # ------------------------------------------------------------------ #
    # subclass hook
    # ------------------------------------------------------------------ #

    @abstractmethod
    def build(self, context: HedgeContext) -> StrategyHypothesis:
        """Build this family's proposal for ``context``.

        Return a viable hypothesis (use :meth:`viable`), return
        :meth:`not_viable` directly, or raise :class:`SelfRejection` to reject
        the family with a reason. Implemented by each concrete agent
        (P4-BE-2..5); callers use :meth:`propose`.
        """

    # ------------------------------------------------------------------ #
    # helpers — fill the fields every family shares
    # ------------------------------------------------------------------ #

    def viable(
        self,
        context: HedgeContext,
        *,
        action: HedgeAction,
        cost: float,
        rationale: str,
        legs: Sequence[OptionLeg] = (),
        hedge_metrics: HedgeMetrics | None = None,
        payoff_profile: Sequence[PayoffPoint] = (),
        liquidity: str | None = None,
        risks: Sequence[str] = (),
        tradeoffs: Sequence[str] = (),
        rejection_conditions: Sequence[str] = (),
    ) -> StrategyHypothesis:
        """A VIABLE hypothesis for this family, ``cycle_id`` / ``strategy`` wired in."""
        return StrategyHypothesis(
            cycle_id=context.cycle_id,
            strategy=self.strategy,
            action=action,
            viable=True,
            legs=list(legs),
            cost=cost,
            hedge_metrics=hedge_metrics or HedgeMetrics(),
            payoff_profile=list(payoff_profile),
            liquidity=liquidity,
            risks=list(risks),
            tradeoffs=list(tradeoffs),
            rationale=rationale,
            rejection_conditions=list(rejection_conditions),
        )

    def not_viable(
        self,
        context: HedgeContext,
        reason: str,
        *,
        action: HedgeAction = HedgeAction.NO_TRADE,
        rationale: str | None = None,
        rejection_conditions: Sequence[str] = (),
    ) -> StrategyHypothesis:
        """A NOT_VIABLE hypothesis: the agent rejected its own family (BRD §16).

        ``reason`` is required and becomes ``rejection_reason``; it also seeds
        ``rationale`` when the caller gives none.
        """
        if not reason or not reason.strip():
            raise ValueError("a NOT_VIABLE hypothesis needs a non-empty reason")
        return StrategyHypothesis(
            cycle_id=context.cycle_id,
            strategy=self.strategy,
            action=action,
            viable=False,
            cost=0.0,
            rationale=rationale or reason,
            rejection_reason=reason,
            rejection_conditions=list(rejection_conditions),
        )
