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
