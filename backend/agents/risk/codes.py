"""Deterministic risk-engine violation codes — Phase 5 (BRD §19–20).

Every hard check in the risk gate that can fail maps to exactly one stable
:class:`ViolationCode`. The code is the machine-readable half of a rejection:
the frontend and the ``risk_checks`` audit row key off it, and the downstream
LLM Risk Agent (P5-BE-8) may never clear a decision that still carries one.

Values follow the ``enums.py`` convention — a ``str`` enum whose value equals
its member name, so the wire form is a stable, self-describing token. They are
pinned here and asserted in ``tests/agents/test_risk_limits_engine.py`` to
guard against a silent rename breaking the audit trail.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["ViolationCode"]


class ViolationCode(str, Enum):
    """A single deterministic hard-limit breach raised by the risk engine."""

    #: Cash cost of the hedge exceeds ``max_hedge_budget_pct · total_value`` (P5-BE-1).
    HEDGE_BUDGET_EXCEEDED = "HEDGE_BUDGET_EXCEEDED"

    #: Proposed hedge ratio exceeds the policy ceiling (P5-BE-2).
    MAX_HEDGE_RATIO_EXCEEDED = "MAX_HEDGE_RATIO_EXCEEDED"

    #: Gross option-leg notional exceeds the portfolio's total value (P5-BE-2).
    MAX_NOTIONAL_EXCEEDED = "MAX_NOTIONAL_EXCEEDED"

    #: Option contracts on a single underlying are not covered by the share
    #: position held in that name — an over-hedged or naked single-name bet
    #: rather than a hedge (P5-BE-2).
    POSITION_LIMIT_EXCEEDED = "POSITION_LIMIT_EXCEEDED"

    #: Cash cost of the hedge exceeds the account's available buying power (P5-BE-3).
    INSUFFICIENT_BUYING_POWER = "INSUFFICIENT_BUYING_POWER"

    #: A hedge leg has no tradeable quotes, or its bid/ask spread / open interest
    #: is past the liquidity threshold (P5-BE-3).
    ILLIQUID_CONTRACT = "ILLIQUID_CONTRACT"

    #: A hedge leg does not match any contract surfaced by the Options Analysis
    #: Agent — it cannot be validated as a real, tradeable option (P5-BE-4).
    UNKNOWN_CONTRACT = "UNKNOWN_CONTRACT"

    #: A hedge leg's expiration is already in the past (P5-BE-4).
    CONTRACT_EXPIRED = "CONTRACT_EXPIRED"

    #: A hedge leg expires inside the minimum time-to-expiry window (P5-BE-4).
    EXPIRY_WINDOW_VIOLATION = "EXPIRY_WINDOW_VIOLATION"

    #: The proposal's net delta is outside the policy band for a hedge overlay
    #: — it adds directional exposure or over-hedges the underlying (P5-BE-5).
    NET_DELTA_OUT_OF_BOUNDS = "NET_DELTA_OUT_OF_BOUNDS"

    #: A multi-leg structure is internally inconsistent — inverted spread
    #: strikes, a collar missing a leg, or legs spanning underlyings (P5-BE-5).
    MULTILEG_INCONSISTENT = "MULTILEG_INCONSISTENT"

    #: A leg's limit price is outside the allowed percentage band around the
    #: contract mid (P5-BE-6).
    PRICE_BAND_EXCEEDED = "PRICE_BAND_EXCEEDED"
