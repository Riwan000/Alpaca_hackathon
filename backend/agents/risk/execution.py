"""Execution-tolerance / price-band screen — task **P5-BE-6** (BRD §19).

:func:`check_price_band` rejects a plan whose leg limit prices stray too far
from the current contract mid. A limit set well above mid overpays (and can
fill into a stale quote); one set well below mid will never fill and stalls the
hedge. Only legs that actually carry a ``limit_price`` are screened — a
market-order leg has no band to break. Exactly on the band edge passes.

Pure function. No LLM, no I/O.
"""

from __future__ import annotations

from backend.agents.risk._match import candidate_mid, match_candidate
from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.engine import CheckOutcome
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

__all__ = ["DEFAULT_MAX_PRICE_DEVIATION_PCT", "check_price_band"]

#: How far a leg's limit price may sit from the contract mid, as a fraction of
#: mid. A 5 % band is tight enough to catch a fat-fingered or stale price while
#: still allowing a normal marketable limit.
DEFAULT_MAX_PRICE_DEVIATION_PCT: float = 0.05

_EXECUTION = "EXECUTION"
_PRICE_BAND_CHECK = "price_band"


def check_price_band(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    max_deviation_pct: float | None = None,
) -> CheckOutcome:
    """Fail when a leg's limit price is outside the band around mid (P5-BE-6).

    ``max_deviation_pct`` defaults to :data:`DEFAULT_MAX_PRICE_DEVIATION_PCT`.
    Deviation is ``|limit_price - mid| / mid``. Legs with no ``limit_price``, or
    with no usable mid to price against, are skipped. The first leg past the
    band in leg order is reported.
    """
    band = (
        DEFAULT_MAX_PRICE_DEVIATION_PCT
        if max_deviation_pct is None
        else max_deviation_pct
    )
    screened = 0

    for leg in hypothesis.legs:
        if leg.limit_price is None:
            continue
        candidate = match_candidate(leg, context)
        mid = candidate_mid(candidate) if candidate is not None else None
        if not mid:
            continue

        screened += 1
        deviation = abs(leg.limit_price - mid) / mid
        if deviation > band:
            tag = f"{leg.underlying} {leg.strike:g} {leg.right.value}"
            return CheckOutcome(
                name=_PRICE_BAND_CHECK,
                category=_EXECUTION,
                passed=False,
                code=ViolationCode.PRICE_BAND_EXCEEDED,
                detail=(
                    f"{tag}: limit {leg.limit_price:,.2f} is {deviation:.1%} "
                    f"off mid {mid:,.2f} (band {band:.1%})"
                ),
                observed=deviation,
                limit=band,
            )

    if screened == 0:
        return CheckOutcome(
            name=_PRICE_BAND_CHECK,
            category=_EXECUTION,
            passed=True,
            detail="no limit-priced legs to band-check",
        )

    return CheckOutcome(
        name=_PRICE_BAND_CHECK,
        category=_EXECUTION,
        passed=True,
        detail=f"every limit-priced leg is within {band:.1%} of mid",
    )
