"""Structured observability logging — task P8-BE-3.

Emits structured JSON log lines for every significant event in an autonomous cycle:
- Agent invocation & input/output summaries
- Strategy decisions
- Tool calls
- Risk check verdicts & violations
- Order submissions & execution fills
- Errors & warnings
- Reassessment triggers
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any

logger = logging.getLogger("aegis.observability")


def emit_structured_event(
    cycle_id: str,
    event_type: str,
    **payload: Any,
) -> dict[str, Any]:
    """Emit a structured JSON log record with shared cycle_id and ISO timestamp."""
    record: dict[str, Any] = {
        "cycle_id": cycle_id,
        "event_type": event_type,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        **payload,
    }
    logger.info(json.dumps(record, default=str))
    return record


class CycleObserver:
    """Convenience wrapper for emitting structured logs for a specific cycle."""

    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id

    def agent_invocation(self, agent_name: str, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "agent_invocation", agent_name=agent_name, **kwargs)

    def input_summary(self, summary: str | dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "input_summary", summary=summary, **kwargs)

    def output(self, agent_name: str, output: Any, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "output", agent_name=agent_name, output=output, **kwargs)

    def decision(self, decision_type: str, strategy: str, rationale: str, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(
            self.cycle_id,
            "decision",
            decision_type=decision_type,
            strategy=strategy,
            rationale=rationale,
            **kwargs,
        )

    def tool_call(self, tool_name: str, args: dict[str, Any], result: Any = None, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "tool_call", tool_name=tool_name, args=args, result=result, **kwargs)

    def risk_check(self, verdict: str, violations: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "risk_check", verdict=verdict, violations=violations or [], **kwargs)

    def order(self, order_id: str, order_class: str, status: str, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "order", order_id=order_id, order_class=order_class, status=status, **kwargs)

    def fill(self, order_id: str, leg_symbol: str, qty: float, price: float, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "fill", order_id=order_id, leg_symbol=leg_symbol, qty=qty, price=price, **kwargs)

    def error(self, error: str, error_type: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(self.cycle_id, "error", error=error, error_type=error_type, **kwargs)

    def reassessment_trigger(self, trigger_type: str, observed: Any = None, threshold: Any = None, **kwargs: Any) -> dict[str, Any]:
        return emit_structured_event(
            self.cycle_id,
            "reassessment_trigger",
            trigger_type=trigger_type,
            observed=observed,
            threshold=threshold,
            **kwargs,
        )
