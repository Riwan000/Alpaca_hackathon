"""Risk limit checks for option hedge proposals (P2-BE-15).

Three deterministic hard limits are enforced before any LLM or execution call:

- **Max hedge ratio** — the proposed notional hedge must not exceed a configurable
  multiple of the portfolio exposure (default 1.0 = fully hedged).
- **Max notional** — the cash value of the hedge leg(s) must not exceed an
  absolute cap.
- **Budget** — the cash cost of the position must not exceed the available
  hedge budget.

Each check returns a :class:`LimitResult`. A clean run produces a result with
``passed=True``; a breach produces ``passed=False`` and a human-readable
``reason`` that explains exactly which limit was exceeded and by how much.
``exactly at limit`` always passes (``<=`` / ``>=`` as appropriate).

The top-level helper :func:`check_all_limits` runs every check in order and
aggregates the violations into a :class:`LimitReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LimitResult",
    "LimitReport",
    "check_hedge_ratio",
    "check_notional",
    "check_budget",
    "check_all_limits",
]


# ---------------------------------------------------------------------------
# Result primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitResult:
    """Outcome of a single limit check."""

    passed: bool
    """``True`` when within (or exactly at) the limit."""

    reason: str
    """Human-readable explanation; empty string when ``passed=True``."""

    @property
    def violated(self) -> bool:
        """Convenience alias for ``not passed``."""
        return not self.passed


@dataclass
class LimitReport:
    """Aggregated results of all limit checks for a single proposal."""

    results: list[LimitResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """``True`` only when every individual check passed."""
        return all(r.passed for r in self.results)

    @property
    def violations(self) -> list[LimitResult]:
        """The subset of results that represent breaches."""
        return [r for r in self.results if r.violated]

    @property
    def violation_reasons(self) -> list[str]:
        """Plain-text reasons for every breach."""
        return [r.reason for r in self.violations]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_hedge_ratio(
    proposed_ratio: float,
    max_ratio: float,
) -> LimitResult:
    """Check that *proposed_ratio* does not exceed *max_ratio*.

    Both arguments must be non-negative.  Exactly at the limit (``==``) passes.

    Parameters
    ----------
    proposed_ratio:
        The hedge ratio implied by the proposed position
        (``hedge notional / exposure notional``).
    max_ratio:
        The policy ceiling on the hedge ratio (e.g. ``1.0`` for a full hedge).
    """
    if proposed_ratio < 0:
        raise ValueError(
            f"proposed_ratio must be non-negative, got {proposed_ratio!r}"
        )
    if max_ratio < 0:
        raise ValueError(f"max_ratio must be non-negative, got {max_ratio!r}")

    if proposed_ratio <= max_ratio:
        return LimitResult(passed=True, reason="")

    reason = (
        f"hedge ratio {proposed_ratio:.4f} exceeds max allowed {max_ratio:.4f} "
        f"(over by {proposed_ratio - max_ratio:.4f})"
    )
    return LimitResult(passed=False, reason=reason)


def check_notional(
    proposed_notional: float,
    max_notional: float,
) -> LimitResult:
    """Check that the absolute proposed cash notional does not exceed *max_notional*.

    ``proposed_notional`` is taken by magnitude so signed notionals work too.
    Exactly at the limit passes.

    Parameters
    ----------
    proposed_notional:
        The gross cash value of the proposed hedge (may be signed).
    max_notional:
        Absolute ceiling on the hedge notional (must be ``>= 0``).
    """
    if max_notional < 0:
        raise ValueError(
            f"max_notional must be non-negative, got {max_notional!r}"
        )

    abs_notional = abs(proposed_notional)
    if abs_notional <= max_notional:
        return LimitResult(passed=True, reason="")

    reason = (
        f"proposed notional {abs_notional:,.2f} exceeds max allowed "
        f"{max_notional:,.2f} (over by {abs_notional - max_notional:,.2f})"
    )
    return LimitResult(passed=False, reason=reason)


def check_budget(
    cash_cost: float,
    budget: float,
) -> LimitResult:
    """Check that *cash_cost* does not exceed the available *budget*.

    Both values must be non-negative.  Exactly at the budget limit passes.

    Parameters
    ----------
    cash_cost:
        Actual cash outlay for the hedge (``premium * contracts * multiplier``).
    budget:
        Maximum cash available for this hedge leg.
    """
    if cash_cost < 0:
        raise ValueError(f"cash_cost must be non-negative, got {cash_cost!r}")
    if budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget!r}")

    if cash_cost <= budget:
        return LimitResult(passed=True, reason="")

    reason = (
        f"cash cost {cash_cost:,.2f} exceeds budget {budget:,.2f} "
        f"(over by {cash_cost - budget:,.2f})"
    )
    return LimitResult(passed=False, reason=reason)


# ---------------------------------------------------------------------------
# Aggregate helper
# ---------------------------------------------------------------------------


def check_all_limits(
    *,
    proposed_ratio: float,
    max_ratio: float,
    proposed_notional: float,
    max_notional: float,
    cash_cost: float,
    budget: float,
) -> LimitReport:
    """Run all three limit checks and collect results into a :class:`LimitReport`.

    Parameters
    ----------
    proposed_ratio:
        Hedge ratio of the proposed position.
    max_ratio:
        Maximum allowable hedge ratio.
    proposed_notional:
        Gross cash notional of the proposed position.
    max_notional:
        Maximum allowable notional.
    cash_cost:
        Cash outlay (``premium * contracts * multiplier``).
    budget:
        Available hedge budget.
    """
    report = LimitReport()
    report.results.append(check_hedge_ratio(proposed_ratio, max_ratio))
    report.results.append(check_notional(proposed_notional, max_notional))
    report.results.append(check_budget(cash_cost, budget))
    return report
