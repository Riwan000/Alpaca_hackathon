"""Pre-flight validation — re-check the plan the instant before submit.

Task **P5-BE-11** (BRD §21). Time passes between the risk gate approving a plan
and the order actually going out: a quote goes stale, the contract mid drifts,
buying power gets consumed by another fill. :func:`run_preflight` re-runs the
cheap deterministic gates against a *fresh* context and returns an abort the
moment one fails — the caller then skips the submit entirely and logs the
reason, so no order is ever sent on a plan that no longer holds.

Checks, first failure wins:

1. **contract** — every leg still matches an analyzed candidate and has not
   expired as of ``now``;
2. **stale quote** — the fresh context is not older than ``max_quote_age``;
3. **price drift** — no leg's plan limit price is further from the current mid
   than the plan's ``price_tolerance_pct`` band;
4. **buying power** — the plan's estimated cost still fits the account.

Pure function. No LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.agents.risk._match import candidate_mid, match_candidate
from backend.models.execution import ExecutionPlan
from backend.models.hedge_context import HedgeContext

__all__ = ["DEFAULT_MAX_QUOTE_AGE", "PreflightResult", "run_preflight"]

#: How old the re-fetched context may be before its quotes count as stale. A
#: hedge decision that took longer than this to reach submit is re-evaluated,
#: not fired blind.
DEFAULT_MAX_QUOTE_AGE: timedelta = timedelta(minutes=5)

# Stable abort codes — they land in the ``execution_failures.detail`` blob.
_UNKNOWN_CONTRACT = "UNKNOWN_CONTRACT"
_CONTRACT_EXPIRED = "CONTRACT_EXPIRED"
_STALE_QUOTE = "STALE_QUOTE"
_PRICE_DRIFT = "PRICE_DRIFT"
_INSUFFICIENT_BUYING_POWER = "INSUFFICIENT_BUYING_POWER"


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of the pre-flight pass.

    ``ok`` is ``True`` only when every check passed. A failing result carries a
    stable :attr:`code` and a human ``reason`` for the log / audit row.
    """

    ok: bool
    reason: str
    code: str | None = None

    def __post_init__(self) -> None:
        if self.ok and self.code is not None:
            raise ValueError("a passing pre-flight result carries no code")
        if not self.ok and not self.code:
            raise ValueError("a failing pre-flight result must carry a code")


def run_preflight(
    plan: ExecutionPlan,
    context: HedgeContext,
    *,
    now: datetime | None = None,
    max_quote_age: timedelta | None = None,
) -> PreflightResult:
    """Re-validate ``plan`` against a fresh ``context`` just before submit.

    Args:
        plan: the plan about to be submitted.
        context: a freshly re-assembled :class:`HedgeContext` (new quotes,
            current buying power).
        now: the wall clock to age the context against; defaults to
            ``datetime.now(timezone.utc)``.
        max_quote_age: staleness ceiling for the context; defaults to
            :data:`DEFAULT_MAX_QUOTE_AGE`.

    Returns:
        :class:`PreflightResult` — ``ok=True`` to proceed, else an abort with a
        code and reason. The caller must not submit on a non-``ok`` result.
    """
    clock = now or datetime.now(timezone.utc)
    age_limit = max_quote_age or DEFAULT_MAX_QUOTE_AGE
    today = clock.date()

    # 1. contract validity + expiration
    for leg in plan.legs:
        tag = f"{leg.underlying} {leg.strike:g} {leg.right.value} exp {leg.expiration.isoformat()}"
        if match_candidate(leg, context) is None:
            return PreflightResult(
                ok=False,
                code=_UNKNOWN_CONTRACT,
                reason=f"{tag}: no matching contract in the fresh candidate set",
            )
        if (leg.expiration - today).days < 0:
            return PreflightResult(
                ok=False,
                code=_CONTRACT_EXPIRED,
                reason=f"{tag}: contract expired before submit",
            )

    # 2. stale quote
    ts = context.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = clock - ts
    if age > age_limit:
        return PreflightResult(
            ok=False,
            code=_STALE_QUOTE,
            reason=(
                f"context is {age.total_seconds():.0f}s old, past the "
                f"{age_limit.total_seconds():.0f}s staleness limit"
            ),
        )

    # 3. price drift since approval
    band = plan.constraints.price_tolerance_pct
    for leg in plan.legs:
        if leg.limit_price is None:
            continue
        candidate = match_candidate(leg, context)
        mid = candidate_mid(candidate) if candidate is not None else None
        if not mid:
            continue
        deviation = abs(leg.limit_price - mid) / mid
        if deviation > band:
            tag = f"{leg.underlying} {leg.strike:g} {leg.right.value}"
            return PreflightResult(
                ok=False,
                code=_PRICE_DRIFT,
                reason=(
                    f"{tag}: mid moved to {mid:,.2f}, {deviation:.1%} from the "
                    f"approved limit {leg.limit_price:,.2f} (band {band:.1%})"
                ),
            )

    # 4. buying power
    available = context.portfolio_state.buying_power
    if plan.estimated_cost > available:
        return PreflightResult(
            ok=False,
            code=_INSUFFICIENT_BUYING_POWER,
            reason=(
                f"estimated cost {plan.estimated_cost:,.2f} now exceeds buying "
                f"power {available:,.2f}"
            ),
        )

    return PreflightResult(ok=True, reason="pre-flight checks passed")
