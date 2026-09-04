"""Execution Agent — Phase 5 (BRD §21–23).

Turns an approved :class:`~backend.models.risk.RiskDecision` into a submitted
order and a truthful terminal report:

* :mod:`~backend.agents.execution.plan` — build the
  :class:`~backend.models.execution.ExecutionPlan` from the approved (and
  possibly ``MODIFY``-adjusted) hypothesis (P5-BE-10);
* :mod:`~backend.agents.execution.preflight` — re-check contract, price and
  buying power the instant before submit; abort (no order sent) on drift
  (P5-BE-11);
* :func:`~backend.integrations.alpaca.orders.submit_plan` — one combo order,
  legged fallback only when combos are unsupported (P5-BE-12);
* :mod:`~backend.agents.execution.result` — map the broker order to
  ``FILLED`` / ``PARTIALLY_FILLED`` / ``FAILED`` / ``CANCELLED``, record the
  legging-risk recovery action, and persist the fills (P5-BE-13, P5-BE-14).
"""

from __future__ import annotations

from backend.agents.execution.plan import ExecutionPlanError, build_execution_plan
from backend.agents.execution.preflight import (
    DEFAULT_MAX_QUOTE_AGE,
    PreflightResult,
    run_preflight,
)
from backend.agents.execution.result import (
    RECOVERY_CANCEL_UNFILLED_LEGS,
    RECOVERY_MANUAL_REVIEW,
    RECOVERY_NONE,
    RECOVERY_UNWIND_FILLED_LEGS,
    ExecutionResultError,
    build_execution_result,
    map_broker_status,
    persist_execution_result,
)

__all__ = [
    "DEFAULT_MAX_QUOTE_AGE",
    "RECOVERY_CANCEL_UNFILLED_LEGS",
    "RECOVERY_MANUAL_REVIEW",
    "RECOVERY_NONE",
    "RECOVERY_UNWIND_FILLED_LEGS",
    "ExecutionPlanError",
    "ExecutionResultError",
    "PreflightResult",
    "build_execution_plan",
    "build_execution_result",
    "map_broker_status",
    "persist_execution_result",
    "run_preflight",
]
