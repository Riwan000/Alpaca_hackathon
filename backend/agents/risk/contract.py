"""Contract-validity + expiration screens — task **P5-BE-4** (BRD §19).

* :func:`check_contract_validity` — every hedge leg must match a contract the
  Options Analysis Agent actually surfaced. A leg that matches nothing cannot
  be validated as a real, tradeable option and is rejected.
* :func:`check_expiration_window` — a leg whose expiration is already in the
  past is rejected; so is one that expires inside the minimum time-to-expiry
  window (a hedge that decays out from under the position before it can work).
  Exactly ``min_days`` to expiry passes.

"Now" is :attr:`context.timestamp` — the analysis snapshot time — so the checks
are deterministic and replayable from a recorded context. Both functions are
pure. No LLM, no I/O.
"""

from __future__ import annotations

from backend.agents.risk._match import match_candidate
from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.engine import CheckOutcome
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

__all__ = [
    "DEFAULT_MIN_EXPIRY_DAYS",
    "check_contract_validity",
    "check_expiration_window",
]

#: Minimum calendar days to expiry a hedge leg must carry. A shorter-dated leg
#: is rejected — it decays too fast to be a hedge. Matches the pre-filter
#: minimum tenor so the risk gate never contradicts it.
DEFAULT_MIN_EXPIRY_DAYS: int = 7

_OPTIONS = "OPTIONS"
_VALIDITY_CHECK = "contract_validity"
_EXPIRY_CHECK = "expiration_window"


def check_contract_validity(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
) -> CheckOutcome:
    """Fail when a hedge leg matches no analyzed contract (P5-BE-4).

    The only deterministic evidence a contract is real is that the Options
    Analysis Agent surfaced it in ``context.option_candidates``. A leg matching
    none of them — wrong strike, wrong expiry, an unknown underlying — is
    rejected. The first unmatched leg in leg order is reported. A hypothesis
    with no legs passes.
    """
    for leg in hypothesis.legs:
        if match_candidate(leg, context) is None:
            tag = (
                f"{leg.underlying} {leg.strike:g} {leg.right.value} "
                f"exp {leg.expiration.isoformat()}"
            )
            return CheckOutcome(
                name=_VALIDITY_CHECK,
                category=_OPTIONS,
                passed=False,
                code=ViolationCode.UNKNOWN_CONTRACT,
                detail=(
                    f"{tag}: no matching contract in the analyzed candidate set"
                ),
            )

    return CheckOutcome(
        name=_VALIDITY_CHECK,
        category=_OPTIONS,
        passed=True,
        detail="every hedge leg matches an analyzed contract",
    )


def check_expiration_window(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    min_days: int | None = None,
) -> CheckOutcome:
    """Fail on an expired leg or one expiring inside the min window (P5-BE-4).

    ``min_days`` defaults to :data:`DEFAULT_MIN_EXPIRY_DAYS`. Days-to-expiry is
    ``leg.expiration - context.timestamp.date()``: negative → expired
    (:attr:`ViolationCode.CONTRACT_EXPIRED`); ``0 <= days < min_days`` →
    :attr:`ViolationCode.EXPIRY_WINDOW_VIOLATION`; ``days >= min_days`` passes.
    The first offending leg in leg order is reported; a hypothesis with no legs
    passes.
    """
    floor = DEFAULT_MIN_EXPIRY_DAYS if min_days is None else min_days
    today = context.timestamp.date()

    for leg in hypothesis.legs:
        days = (leg.expiration - today).days
        tag = f"{leg.underlying} {leg.strike:g} {leg.right.value}"

        if days < 0:
            return CheckOutcome(
                name=_EXPIRY_CHECK,
                category=_OPTIONS,
                passed=False,
                code=ViolationCode.CONTRACT_EXPIRED,
                detail=(
                    f"{tag}: expired {-days} day(s) ago "
                    f"(expiry {leg.expiration.isoformat()})"
                ),
                observed=float(days),
                limit=float(floor),
            )

        if days < floor:
            return CheckOutcome(
                name=_EXPIRY_CHECK,
                category=_OPTIONS,
                passed=False,
                code=ViolationCode.EXPIRY_WINDOW_VIOLATION,
                detail=(
                    f"{tag}: {days} day(s) to expiry is inside the "
                    f"{floor}-day minimum window"
                ),
                observed=float(days),
                limit=float(floor),
            )

    return CheckOutcome(
        name=_EXPIRY_CHECK,
        category=_OPTIONS,
        passed=True,
        detail=f"every hedge leg has at least {floor} day(s) to expiry",
    )
