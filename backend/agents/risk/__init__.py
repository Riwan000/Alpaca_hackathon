"""Risk-gate layer — Phase 5 (BRD §19–20).

The non-negotiable safety layer between the Strategy Manager and execution. The
deterministic risk engine (:mod:`backend.agents.risk.engine`) runs pure
hard-limit checks — hedge budget (P5-BE-1), position limits / max hedge ratio /
max notional (P5-BE-2), and the rest of P5-BE-3..6 — before the LLM Risk Agent
(P5-BE-8) is ever consulted. A failing :class:`CheckOutcome` always carries a
:class:`ViolationCode`, and the LLM may not clear a decision that still holds one.
"""

from __future__ import annotations

from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.engine import (
    DEFAULT_MAX_HEDGE_RATIO,
    CheckOutcome,
    RiskEngineLimits,
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
    run_limit_checks,
)

__all__ = [
    "DEFAULT_MAX_HEDGE_RATIO",
    "CheckOutcome",
    "RiskEngineLimits",
    "ViolationCode",
    "check_hedge_budget",
    "check_max_hedge_ratio",
    "check_max_notional",
    "check_position_limit",
    "run_limit_checks",
]
