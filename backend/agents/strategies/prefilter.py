"""Deterministic pre-filter for strategy hypotheses — task P4-BE-6 (BRD §17).

Between the four strategy agents (P4-BE-2..5) and the LLM Strategy Manager
(P4-BE-7..9) sits one deterministic gate: a *viable* hypothesis that breaches a
hard budget or risk limit is dropped here, with a logged reason, so the manager
never spends a prompt reasoning about a structure the book cannot take on.

The three limits are the ones :mod:`backend.quant.risk_limits` already defines
(P2-BE-15):

* **budget** — ``cost`` may not exceed ``max_hedge_budget_pct · total_value``;
* **hedge ratio** — ``hedge_metrics.hedge_ratio`` may not exceed the objective's
  ``target_hedge_ratio`` (or :data:`DEFAULT_MAX_HEDGE_RATIO` — fully hedged —
  when the objective asks for less or names no target);
* **notional** — the gross contract notional of the option legs
  (``Σ quantity · strike · 100``) may not exceed the portfolio's total value.

:func:`prefilter` runs every check over each viable hypothesis and returns a
:class:`PrefilterResult` splitting them into ``kept`` (what the manager sees) and
``dropped`` (each with its human-readable reasons). A NOT_VIABLE hypothesis is a
rejected family, not a proposal to screen, so it passes through untouched — the
manager still needs it for the all-rejected → ``NO_TRADE`` path (P4-BE-7).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from backend.models.enums import StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis
from backend.quant.payoff import OPTION_MULTIPLIER
from backend.quant.risk_limits import check_all_limits

__all__ = [
    "DEFAULT_MAX_HEDGE_RATIO",
    "PrefilterLimits",
    "DroppedHypothesis",
    "PrefilterResult",
    "hypothesis_notional",
    "prefilter",
]

logger = logging.getLogger(__name__)

#: Hedge-ratio ceiling when the objective names no higher target: never let a
#: hedge overlay cover more than 100% of the exposure it hedges.
DEFAULT_MAX_HEDGE_RATIO: float = 1.0


def hypothesis_notional(hypothesis: StrategyHypothesis) -> float:
    """Gross contract notional of the option legs — ``Σ quantity · strike · 100``.

    ``quantity`` is always positive (direction lives in ``side``), so this is the
    absolute notional the structure controls, long and short legs added. A
    hypothesis with no legs (No-Hedge, or any NOT_VIABLE family) is ``0.0``.
    """
    return float(
        sum(
            leg.quantity * leg.strike * OPTION_MULTIPLIER
            for leg in hypothesis.legs
        )
    )


@dataclass(frozen=True)
class PrefilterLimits:
    """The three hard limits a hypothesis is screened against.

    Build the context-derived defaults with :meth:`from_context`, then override
    any field at the call site (a test forcing an over-budget drop, say).
    """

    max_hedge_ratio: float
    max_notional: float
    budget: float

    @classmethod
    def from_context(cls, context: HedgeContext) -> PrefilterLimits:
        """Derive the limits from the objective and portfolio in ``context``."""
        objective = context.objective
        total_value = max(0.0, context.portfolio_state.total_value)
        target = objective.target_hedge_ratio or 0.0
        return cls(
            max_hedge_ratio=max(DEFAULT_MAX_HEDGE_RATIO, target),
            max_notional=total_value,
            budget=objective.max_hedge_budget_pct * total_value,
        )


@dataclass(frozen=True)
class DroppedHypothesis:
    """A hypothesis the pre-filter removed, with every limit it breached."""

    hypothesis: StrategyHypothesis
    reasons: tuple[str, ...]

    @property
    def strategy(self) -> StrategyType:
        """The hedge family that was screened out."""
        return self.hypothesis.strategy


@dataclass(frozen=True)
class PrefilterResult:
    """The split the Strategy Manager consumes: ``kept`` proposals, ``dropped`` ones."""

    kept: tuple[StrategyHypothesis, ...]
    dropped: tuple[DroppedHypothesis, ...]

    @property
    def kept_strategies(self) -> tuple[StrategyType, ...]:
        """Families that reach the manager, in input order."""
        return tuple(h.strategy for h in self.kept)

    @property
    def dropped_strategies(self) -> tuple[StrategyType, ...]:
        """Families the pre-filter removed, in input order."""
        return tuple(d.strategy for d in self.dropped)

    def was_dropped(self, strategy: StrategyType) -> bool:
        """True when the ``strategy`` family was screened out."""
        return strategy in self.dropped_strategies

    def reasons_for(self, strategy: StrategyType) -> tuple[str, ...]:
        """The breach reasons recorded for ``strategy`` — empty if it was kept."""
        for dropped in self.dropped:
            if dropped.strategy is strategy:
                return dropped.reasons
        return ()


def _breaches(
    hypothesis: StrategyHypothesis, limits: PrefilterLimits
) -> list[str]:
    """Every limit ``hypothesis`` breaches under ``limits`` — empty when clean."""
    report = check_all_limits(
        proposed_ratio=hypothesis.hedge_metrics.hedge_ratio or 0.0,
        max_ratio=limits.max_hedge_ratio,
        proposed_notional=hypothesis_notional(hypothesis),
        max_notional=limits.max_notional,
        cash_cost=hypothesis.cost,
        budget=limits.budget,
    )
    return report.violation_reasons


def prefilter(
    hypotheses: Iterable[StrategyHypothesis],
    context: HedgeContext,
    *,
    limits: PrefilterLimits | None = None,
) -> PrefilterResult:
    """Screen ``hypotheses`` against the hard limits before the Strategy Manager.

    Every viable hypothesis whose cost, hedge ratio or notional breaches
    ``limits`` (context-derived via :meth:`PrefilterLimits.from_context` when
    omitted) is moved to :attr:`PrefilterResult.dropped` with its reasons and a
    ``WARNING`` log line; the rest — viable within limits, plus every NOT_VIABLE
    family untouched — land in :attr:`PrefilterResult.kept` in input order.

    Raises:
        ValueError: a hypothesis carries a different ``cycle_id`` than
            ``context`` — a wiring bug, not a limit breach.
    """
    resolved = limits or PrefilterLimits.from_context(context)
    kept: list[StrategyHypothesis] = []
    dropped: list[DroppedHypothesis] = []

    for hypothesis in hypotheses:
        if hypothesis.cycle_id != context.cycle_id:
            raise ValueError(
                f"hypothesis cycle_id {hypothesis.cycle_id!r} != context "
                f"{context.cycle_id!r}"
            )

        if not hypothesis.viable:
            kept.append(hypothesis)
            continue

        reasons = _breaches(hypothesis, resolved)
        if not reasons:
            kept.append(hypothesis)
            continue

        dropped.append(DroppedHypothesis(hypothesis, tuple(reasons)))
        logger.warning(
            "pre-filter dropped %s (cycle %s) before the manager: %s",
            hypothesis.strategy.value,
            hypothesis.cycle_id,
            "; ".join(reasons),
        )

    return PrefilterResult(tuple(kept), tuple(dropped))
