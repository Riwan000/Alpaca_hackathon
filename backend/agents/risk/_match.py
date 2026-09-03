"""Leg ↔ candidate matching for the P5-BE-3..6 option screens.

The buying-power / liquidity (P5-BE-3), contract-validity (P5-BE-4) and
price-band (P5-BE-6) screens all need the same thing: given a proposed
:class:`~backend.models.common.OptionLeg`, find the
:class:`~backend.models.hedge_context.OptionCandidate` the Options Analysis
Agent surfaced for it, and derive a reference mid price from that quote. Both
helpers are pure and live here so the three screens agree on what "the same
contract" and "the mid" mean.
"""

from __future__ import annotations

import math

from backend.models.common import OptionLeg
from backend.models.hedge_context import HedgeContext, OptionCandidate

__all__ = ["match_candidate", "candidate_mid"]

# A strike is a discrete quantity but arrives as a float; compare with a cent of
# tolerance so 145.0 and 145.00000001 are the same contract.
_STRIKE_ATOL = 0.01


def match_candidate(
    leg: OptionLeg, context: HedgeContext
) -> OptionCandidate | None:
    """The analyzed candidate for ``leg`` — same underlying, right, strike, expiry.

    Returns ``None`` when the Options Analysis Agent surfaced nothing for this
    contract, which every screen treats as "cannot be validated".
    """
    for candidate in context.option_candidates:
        if (
            candidate.underlying == leg.underlying
            and candidate.right is leg.right
            and candidate.expiration == leg.expiration
            and math.isclose(
                candidate.strike, leg.strike, abs_tol=_STRIKE_ATOL
            )
        ):
            return candidate
    return None


def candidate_mid(candidate: OptionCandidate) -> float | None:
    """Reference mid price for ``candidate``.

    ``(bid + ask) / 2`` when both sides are quoted, otherwise the ``premium``
    the analysis agent recorded, otherwise ``None`` (nothing to price against).
    """
    if candidate.bid is not None and candidate.ask is not None:
        return (candidate.bid + candidate.ask) / 2.0
    if candidate.premium > 0:
        return candidate.premium
    return None
