"""Deterministic risk engine — hedge-budget + position-limit checks.

Tasks **P5-BE-1** (hedge-budget) and **P5-BE-2** (position limits, max hedge
ratio, max notional): the first hard gates of the Phase 5 non-negotiable safety
layer (BRD §19). Every function here is pure — it reads a proposed
:class:`~backend.models.strategy.StrategyHypothesis` and the assembled
:class:`~backend.models.hedge_context.HedgeContext`, runs one deterministic
comparison, and returns a :class:`CheckOutcome`. No LLM, no I/O.

An over-budget or over-limit proposal is blocked *here*, before the LLM Risk
Agent (P5-BE-8) is ever called, and the LLM cannot override the failure —
a failing :class:`CheckOutcome` always carries a
:class:`~backend.agents.risk.codes.ViolationCode`.

The numeric comparisons reuse :mod:`backend.quant.risk_limits` (P2-BE-15) so the
"exactly at the limit passes" boundary semantics live in one place; this module
adds the stable violation codes, the audit-row mapping (:meth:`CheckOutcome.to_risk_check`)
and the per-underlying position-coverage check the quant layer does not model.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.risk.codes import ViolationCode
from backend.models.enums import AssetClass, OrderSide
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskCheck
from backend.models.strategy import StrategyHypothesis
from backend.quant.payoff import OPTION_MULTIPLIER
from backend.quant.risk_limits import check_budget, check_hedge_ratio, check_notional

__all__ = [
    "DEFAULT_MAX_HEDGE_RATIO",
    "CheckOutcome",
    "RiskEngineLimits",
    "check_hedge_budget",
    "check_max_hedge_ratio",
    "check_max_notional",
    "check_position_limit",
    "run_limit_checks",
]

#: Hedge-ratio ceiling when the objective names no higher target: a hedge
#: overlay may not cover more than 100% of the exposure it hedges. Matches the
#: pre-filter ceiling (P4-BE-6) so the risk gate never contradicts it.
DEFAULT_MAX_HEDGE_RATIO: float = 1.0

# Stable check names — these land in the ``risk_checks.checks`` audit jsonb and
# the frontend risk checklist (P5-FE-2), so they are part of the contract.
_BUDGET_CHECK = "hedge_budget"
_HEDGE_RATIO_CHECK = "max_hedge_ratio"
_NOTIONAL_CHECK = "max_notional"
_POSITION_CHECK = "position_limit"

# ``RiskCheck.category`` vocabulary (see backend/models/risk.py).
_COST = "COST"
_POSITION_LIMITS = "POSITION_LIMITS"


# --------------------------------------------------------------------------- #
# limits
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskEngineLimits:
    """The hard limits a proposed hedge is screened against.

    Build the context-derived defaults with :meth:`from_context`, then override
    any field at the call site (a test forcing an over-budget rejection, say).
    """

    hedge_budget: float
    """Cash ceiling on the hedge cost — ``max_hedge_budget_pct · total_value``."""

    max_hedge_ratio: float
    """Policy ceiling on the proposed hedge ratio."""

    max_notional: float
    """Absolute ceiling on the gross option-leg notional."""

    @classmethod
    def from_context(cls, context: HedgeContext) -> RiskEngineLimits:
        """Derive the limits from the objective and portfolio in ``context``."""
        objective = context.objective
        total_value = max(0.0, context.portfolio_state.total_value)
        target = objective.target_hedge_ratio or 0.0
        return cls(
            hedge_budget=objective.max_hedge_budget_pct * total_value,
            max_hedge_ratio=max(DEFAULT_MAX_HEDGE_RATIO, target),
            max_notional=total_value,
        )


# --------------------------------------------------------------------------- #
# outcome
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CheckOutcome:
    """Result of one deterministic risk check.

    A passing outcome carries no :attr:`code`; a failing one always does. That
    invariant is what stops the LLM Risk Agent (P5-BE-8) from clearing a
    deterministically-failed plan.
    """

    name: str
    category: str
    passed: bool
    code: ViolationCode | None = None
    detail: str = ""
    observed: float | None = None
    limit: float | None = None

    def __post_init__(self) -> None:
        if self.passed and self.code is not None:
            raise ValueError("a passing check cannot carry a violation code")
        if not self.passed and self.code is None:
            raise ValueError("a failing check must carry a violation code")

    @property
    def violated(self) -> bool:
        """Convenience alias for ``not passed``."""
        return not self.passed

    def to_risk_check(self) -> RiskCheck:
        """Map to the :class:`~backend.models.risk.RiskCheck` audit contract."""
        return RiskCheck(
            name=self.name,
            category=self.category,
            passed=self.passed,
            detail=self.detail or None,
            observed=self.observed,
            limit=self.limit,
        )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _leg_notional(hypothesis: StrategyHypothesis) -> float:
    """Gross contract notional of the option legs — ``Σ quantity · strike · 100``.

    ``quantity`` is always positive (direction lives in ``side``), so long and
    short legs both add. A hypothesis with no legs is ``0.0``.
    """
    return float(
        sum(
            leg.quantity * leg.strike * OPTION_MULTIPLIER
            for leg in hypothesis.legs
        )
    )


def _equity_shares_held(context: HedgeContext, underlying: str) -> float:
    """Total equity shares held of ``underlying`` (magnitude, long or short)."""
    return float(
        sum(
            abs(position.qty)
            for position in context.portfolio_state.positions
            if position.symbol == underlying
            and position.asset_class is AssetClass.EQUITY
        )
    )


def _underlyings_in_order(hypothesis: StrategyHypothesis) -> list[str]:
    """Distinct leg underlyings, in first-seen order."""
    seen: list[str] = []
    for leg in hypothesis.legs:
        if leg.underlying not in seen:
            seen.append(leg.underlying)
    return seen


# --------------------------------------------------------------------------- #
# P5-BE-1 — hedge-budget check
# --------------------------------------------------------------------------- #


def check_hedge_budget(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    limits: RiskEngineLimits | None = None,
) -> CheckOutcome:
    """Fail when the hedge cost exceeds the hedge budget (P5-BE-1).

    Budget is ``objective.max_hedge_budget_pct · portfolio total_value`` unless
    ``limits`` overrides it. Cost exactly equal to the budget passes.
    """
    resolved = limits or RiskEngineLimits.from_context(context)
    result = check_budget(cash_cost=hypothesis.cost, budget=resolved.hedge_budget)

    if result.passed:
        return CheckOutcome(
            name=_BUDGET_CHECK,
            category=_COST,
            passed=True,
            detail=(
                f"hedge cost {hypothesis.cost:,.2f} within budget "
                f"{resolved.hedge_budget:,.2f}"
            ),
            observed=hypothesis.cost,
            limit=resolved.hedge_budget,
        )

    return CheckOutcome(
        name=_BUDGET_CHECK,
        category=_COST,
        passed=False,
        code=ViolationCode.HEDGE_BUDGET_EXCEEDED,
        detail=result.reason,
        observed=hypothesis.cost,
        limit=resolved.hedge_budget,
    )


# --------------------------------------------------------------------------- #
# P5-BE-2 — position limits + max hedge ratio + max notional
# --------------------------------------------------------------------------- #


def check_max_hedge_ratio(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    limits: RiskEngineLimits | None = None,
) -> CheckOutcome:
    """Fail when the proposed hedge ratio exceeds the policy ceiling (P5-BE-2).

    The ceiling is :data:`DEFAULT_MAX_HEDGE_RATIO` (fully hedged) or the
    objective's ``target_hedge_ratio`` when it asks for more. A missing
    ``hedge_metrics.hedge_ratio`` is treated as ``0.0``. Exactly at the ceiling
    passes.
    """
    resolved = limits or RiskEngineLimits.from_context(context)
    proposed = hypothesis.hedge_metrics.hedge_ratio or 0.0
    result = check_hedge_ratio(proposed, resolved.max_hedge_ratio)

    if result.passed:
        return CheckOutcome(
            name=_HEDGE_RATIO_CHECK,
            category=_POSITION_LIMITS,
            passed=True,
            detail=(
                f"hedge ratio {proposed:.4f} within ceiling "
                f"{resolved.max_hedge_ratio:.4f}"
            ),
            observed=proposed,
            limit=resolved.max_hedge_ratio,
        )

    return CheckOutcome(
        name=_HEDGE_RATIO_CHECK,
        category=_POSITION_LIMITS,
        passed=False,
        code=ViolationCode.MAX_HEDGE_RATIO_EXCEEDED,
        detail=result.reason,
        observed=proposed,
        limit=resolved.max_hedge_ratio,
    )


def check_max_notional(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    limits: RiskEngineLimits | None = None,
) -> CheckOutcome:
    """Fail when the gross option-leg notional exceeds the cap (P5-BE-2).

    Notional is ``Σ quantity · strike · 100`` over every leg; the cap is the
    portfolio's total value unless ``limits`` overrides it. Exactly at the cap
    passes.
    """
    resolved = limits or RiskEngineLimits.from_context(context)
    notional = _leg_notional(hypothesis)
    result = check_notional(notional, resolved.max_notional)

    if result.passed:
        return CheckOutcome(
            name=_NOTIONAL_CHECK,
            category=_POSITION_LIMITS,
            passed=True,
            detail=(
                f"leg notional {notional:,.2f} within cap "
                f"{resolved.max_notional:,.2f}"
            ),
            observed=notional,
            limit=resolved.max_notional,
        )

    return CheckOutcome(
        name=_NOTIONAL_CHECK,
        category=_POSITION_LIMITS,
        passed=False,
        code=ViolationCode.MAX_NOTIONAL_EXCEEDED,
        detail=result.reason,
        observed=notional,
        limit=resolved.max_notional,
    )


def check_position_limit(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    limits: RiskEngineLimits | None = None,
) -> CheckOutcome:
    """Fail when option contracts on a name exceed its share coverage (P5-BE-2).

    For each underlying in the hedge legs, the contract count may not exceed
    ``floor(shares_held / 100)``. Hedging a name that is not held at all (or
    holding more contracts than the position covers) is an over-hedged or naked
    single-name bet, not a hedge — the first such underlying, in leg order, is
    reported. A hypothesis with no legs passes.

    Contracts are counted per side (long vs short) and the larger side is what
    must be covered, so a legitimate 1×1 spread or collar on 100 shares passes
    while a 3× protective put or a 2× naked short call on the same 100 shares
    does not.

    ``limits`` is accepted for signature symmetry with the other checks; the
    coverage ceiling is derived from the portfolio, not from ``limits``.
    """
    del limits  # coverage is portfolio-derived; kept for call-site symmetry

    for underlying in _underlyings_in_order(hypothesis):
        legs = [leg for leg in hypothesis.legs if leg.underlying == underlying]
        long_contracts = sum(
            leg.quantity for leg in legs if leg.side is OrderSide.BUY
        )
        short_contracts = sum(
            leg.quantity for leg in legs if leg.side is OrderSide.SELL
        )
        contracts = max(long_contracts, short_contracts)
        shares = _equity_shares_held(context, underlying)
        covered_contracts = shares // OPTION_MULTIPLIER

        if contracts > covered_contracts:
            return CheckOutcome(
                name=_POSITION_CHECK,
                category=_POSITION_LIMITS,
                passed=False,
                code=ViolationCode.POSITION_LIMIT_EXCEEDED,
                detail=(
                    f"{underlying}: {contracts:g} option contract(s) exceed the "
                    f"{covered_contracts:g} covered by the {shares:g} shares held "
                    f"(over by {contracts - covered_contracts:g})"
                ),
                observed=float(contracts),
                limit=float(covered_contracts),
            )

    return CheckOutcome(
        name=_POSITION_CHECK,
        category=_POSITION_LIMITS,
        passed=True,
        detail="every hedged name is covered by the share position held",
    )


def run_limit_checks(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    limits: RiskEngineLimits | None = None,
) -> list[CheckOutcome]:
    """Run the three P5-BE-2 limit checks and return one outcome per limit.

    Order is stable: ``[max_hedge_ratio, max_notional, position_limit]``. Each
    breach carries its own distinct :class:`ViolationCode`, so a plan that
    trips more than one limit is rejected with every reason, not just the first.
    """
    resolved = limits or RiskEngineLimits.from_context(context)
    return [
        check_max_hedge_ratio(hypothesis, context, limits=resolved),
        check_max_notional(hypothesis, context, limits=resolved),
        check_position_limit(hypothesis, context, limits=resolved),
    ]
