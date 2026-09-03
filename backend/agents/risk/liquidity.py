"""Buying-power + liquidity screens — task **P5-BE-3** (BRD §19).

Two hard gates that sit next to the P5-BE-1/2 limits:

* :func:`check_buying_power` — the hedge's cash cost may not exceed the
  account's available buying power. Cost exactly equal to buying power passes.
* :func:`check_liquidity` — every hedge leg must be genuinely tradeable: it
  needs live quotes, a bid/ask spread inside the threshold, and open interest
  above the floor. A leg with *no* quotes is rejected outright; a
  wide-but-tradeable spread or thin-but-present open interest is a
  :attr:`~backend.agents.risk.engine.CheckOutcome.warning`, not a block.

Both functions are pure — a proposed hypothesis plus the assembled
:class:`~backend.models.hedge_context.HedgeContext` in, one
:class:`~backend.agents.risk.engine.CheckOutcome` out. No LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.risk._match import candidate_mid, match_candidate
from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.engine import CheckOutcome
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

__all__ = [
    "LiquidityThresholds",
    "check_buying_power",
    "check_liquidity",
]

_COST = "COST"
_OPTIONS = "OPTIONS"

_BUYING_POWER_CHECK = "buying_power"
_LIQUIDITY_CHECK = "liquidity"


@dataclass(frozen=True)
class LiquidityThresholds:
    """Where a leg stops being liquid enough to trade.

    Relative spread is ``(ask - bid) / mid``. Past ``max_relative_spread`` (or
    below ``min_open_interest``) the leg is blocked; between the warn and fail
    bands it is flagged as a warning.
    """

    max_relative_spread: float = 0.10
    """Bid/ask spread as a fraction of mid above which a leg is illiquid."""

    warn_relative_spread: float = 0.05
    """Spread fraction above which a still-tradeable leg is flagged."""

    min_open_interest: int = 100
    """Open interest below which a leg is illiquid."""

    warn_open_interest: int = 500
    """Open interest below which a still-tradeable leg is flagged."""


_DEFAULT_THRESHOLDS = LiquidityThresholds()


def check_buying_power(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    buying_power: float | None = None,
) -> CheckOutcome:
    """Fail when the hedge cost exceeds available buying power (P5-BE-3).

    Buying power is ``context.portfolio_state.buying_power`` unless overridden.
    Cost exactly equal to buying power passes.
    """
    available = (
        buying_power
        if buying_power is not None
        else context.portfolio_state.buying_power
    )
    cost = hypothesis.cost

    if cost <= available:
        return CheckOutcome(
            name=_BUYING_POWER_CHECK,
            category=_COST,
            passed=True,
            detail=(
                f"hedge cost {cost:,.2f} within buying power {available:,.2f}"
            ),
            observed=cost,
            limit=available,
        )

    return CheckOutcome(
        name=_BUYING_POWER_CHECK,
        category=_COST,
        passed=False,
        code=ViolationCode.INSUFFICIENT_BUYING_POWER,
        detail=(
            f"hedge cost {cost:,.2f} exceeds buying power {available:,.2f} "
            f"(short by {cost - available:,.2f})"
        ),
        observed=cost,
        limit=available,
    )


def check_liquidity(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    thresholds: LiquidityThresholds | None = None,
) -> CheckOutcome:
    """Screen every hedge leg for tradeable liquidity (P5-BE-3).

    A leg with no matching candidate, or a matched candidate with neither a bid
    nor an ask, is rejected as illiquid. A wide spread or thin open interest
    past the hard threshold is also a rejection; past only the warn threshold it
    is a warning. The first hard failure in leg order wins; absent one, a
    warning on any leg is surfaced; absent that, the check passes.
    """
    limits = thresholds or _DEFAULT_THRESHOLDS
    warnings: list[str] = []

    for leg in hypothesis.legs:
        tag = f"{leg.underlying} {leg.strike:g} {leg.right.value}"
        candidate = match_candidate(leg, context)

        if candidate is None or (
            candidate.bid is None and candidate.ask is None
        ):
            return CheckOutcome(
                name=_LIQUIDITY_CHECK,
                category=_OPTIONS,
                passed=False,
                code=ViolationCode.ILLIQUID_CONTRACT,
                detail=f"{tag}: no quotes — the strike is not tradeable",
            )

        mid = candidate_mid(candidate)
        if candidate.bid is not None and candidate.ask is not None and mid:
            rel_spread = (candidate.ask - candidate.bid) / mid
            if rel_spread > limits.max_relative_spread:
                return CheckOutcome(
                    name=_LIQUIDITY_CHECK,
                    category=_OPTIONS,
                    passed=False,
                    code=ViolationCode.ILLIQUID_CONTRACT,
                    detail=(
                        f"{tag}: bid/ask spread {rel_spread:.1%} of mid exceeds "
                        f"{limits.max_relative_spread:.1%}"
                    ),
                    observed=rel_spread,
                    limit=limits.max_relative_spread,
                )
            if rel_spread > limits.warn_relative_spread:
                warnings.append(
                    f"{tag}: bid/ask spread {rel_spread:.1%} of mid is wide"
                )

        oi = candidate.open_interest or 0
        if oi < limits.min_open_interest:
            return CheckOutcome(
                name=_LIQUIDITY_CHECK,
                category=_OPTIONS,
                passed=False,
                code=ViolationCode.ILLIQUID_CONTRACT,
                detail=(
                    f"{tag}: open interest {oi} below the "
                    f"{limits.min_open_interest} floor"
                ),
                observed=float(oi),
                limit=float(limits.min_open_interest),
            )
        if oi < limits.warn_open_interest:
            warnings.append(
                f"{tag}: open interest {oi} is thin "
                f"(< {limits.warn_open_interest})"
            )

    if warnings:
        return CheckOutcome(
            name=_LIQUIDITY_CHECK,
            category=_OPTIONS,
            passed=True,
            warning=True,
            detail="; ".join(warnings),
        )

    return CheckOutcome(
        name=_LIQUIDITY_CHECK,
        category=_OPTIONS,
        passed=True,
        detail="every hedge leg has tradeable quotes within the thresholds",
    )
