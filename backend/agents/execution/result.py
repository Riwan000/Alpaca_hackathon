"""Map a broker order to an :class:`ExecutionResult`, and persist its fills.

Tasks **P5-BE-13** (legging-risk / partial-fill recovery — never report false
success) and **P5-BE-14** (terminal-state mapping + fills persistence),
BRD §23.

* :func:`map_broker_status` — one Alpaca terminal order state → one
  :class:`~backend.models.enums.ExecutionStatus`. A non-terminal state raises,
  so a still-working order can never be reported as done.
* :func:`build_execution_result` — reads the broker order's per-leg fills and
  builds the truthful report: fully filled → ``FILLED``; any leg short or
  unfilled → ``PARTIALLY_FILLED`` with the unfilled leg(s) in ``failed_legs``
  and a ``recovery_action`` recorded; nothing filled → ``CANCELLED`` /
  ``FAILED`` per the broker's reason. A broker that claims ``filled`` while a
  leg shows no fill is still downgraded — the fills are the source of truth.
* :func:`persist_execution_result` — writes the ``orders`` row and one
  ``fills`` row per filled leg (with realized price and slippage) in one
  transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Engine

from backend.db.orders_repo import FillRecord, OrderRecord, OrderRepository, OrderWithFills
from backend.integrations._http import parse_timestamp
from backend.integrations.alpaca.orders import occ_symbol_for_leg
from backend.models.enums import ExecutionStatus, OrderSide
from backend.models.execution import (
    ExecutionPlan,
    ExecutionResult,
    FailedLeg,
    FilledLeg,
)
from backend.quant.payoff import OPTION_MULTIPLIER

__all__ = [
    "RECOVERY_CANCEL_UNFILLED_LEGS",
    "RECOVERY_MANUAL_REVIEW",
    "RECOVERY_NONE",
    "RECOVERY_UNWIND_FILLED_LEGS",
    "ExecutionResultError",
    "build_execution_result",
    "map_broker_status",
    "persist_execution_result",
]

#: Recovery actions recorded on a non-clean fill (P5-BE-13).
RECOVERY_NONE = "NONE"
RECOVERY_CANCEL_UNFILLED_LEGS = "CANCEL_UNFILLED_LEGS"
RECOVERY_UNWIND_FILLED_LEGS = "UNWIND_FILLED_LEGS"
RECOVERY_MANUAL_REVIEW = "MANUAL_REVIEW"

# Alpaca order ``status`` values, grouped by the ExecutionStatus they map to.
_FILLED_STATES = {"filled"}
_PARTIAL_STATES = {"partially_filled"}
_CANCELLED_STATES = {"canceled", "cancelled", "expired", "done_for_day", "replaced"}
_FAILED_STATES = {"rejected", "suspended", "stopped"}
# Everything the broker can say while the order is still live.
_NON_TERMINAL_STATES = {
    "new",
    "accepted",
    "pending_new",
    "accepted_for_bidding",
    "held",
    "pending_cancel",
    "pending_replace",
    "calculated",
}

_EXECUTION_TO_ORDER_STATUS = {
    ExecutionStatus.FILLED: "FILLED",
    ExecutionStatus.PARTIALLY_FILLED: "PARTIALLY_FILLED",
    ExecutionStatus.CANCELLED: "CANCELLED",
    ExecutionStatus.FAILED: "REJECTED",
}


class ExecutionResultError(ValueError):
    """The broker payload cannot be mapped to a terminal :class:`ExecutionResult`."""


def map_broker_status(status: str) -> ExecutionStatus:
    """Map one Alpaca terminal order state to an :class:`ExecutionStatus`.

    Raises:
        ExecutionResultError: ``status`` is a live / non-terminal state (or
            unknown) — there is no truthful terminal result to report yet.
    """
    key = (status or "").strip().lower()
    if key in _FILLED_STATES:
        return ExecutionStatus.FILLED
    if key in _PARTIAL_STATES:
        return ExecutionStatus.PARTIALLY_FILLED
    if key in _CANCELLED_STATES:
        return ExecutionStatus.CANCELLED
    if key in _FAILED_STATES:
        return ExecutionStatus.FAILED
    if key in _NON_TERMINAL_STATES:
        raise ExecutionResultError(
            f"broker order is not in a terminal state yet: {status!r}"
        )
    raise ExecutionResultError(f"unknown broker order status: {status!r}")


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return parse_timestamp(str(value))
    except ValueError:
        return None


def _broker_legs(broker_order: dict[str, Any]) -> list[dict[str, Any]]:
    """The per-leg fill records — the ``legs`` array, or the order itself."""
    legs = broker_order.get("legs")
    if isinstance(legs, list) and legs:
        return [leg for leg in legs if isinstance(leg, dict)]
    return [broker_order]


def _order_ids(broker_order: dict[str, Any], legs: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for candidate in (broker_order, *legs):
        oid = candidate.get("id")
        if oid:
            seen.setdefault(str(oid), None)
    return list(seen)


def build_execution_result(
    plan: ExecutionPlan,
    broker_order: dict[str, Any],
    *,
    now: datetime | None = None,
) -> ExecutionResult:
    """Build the truthful :class:`ExecutionResult` for a terminal broker order.

    ``broker_order`` is an Alpaca order object — a combo parent with a ``legs``
    array, or a single-leg order. Per-leg ``filled_qty`` / ``filled_avg_price``
    drive the outcome; the plan legs supply the expected price for slippage and
    the ordered quantity a fill is measured against.
    """
    clock = now or datetime.now(timezone.utc)
    raw_legs = _broker_legs(broker_order)
    expected_by_symbol = {
        occ_symbol_for_leg(leg): leg for leg in plan.legs
    }

    filled_legs: list[FilledLeg] = []
    failed_legs: list[FailedLeg] = []
    slippages: list[float] = []
    signed_cost = 0.0
    fully_filled = 0
    any_partial = False

    for raw in raw_legs:
        symbol = str(raw.get("symbol") or "").upper()
        plan_leg = expected_by_symbol.get(symbol)
        ordered_qty = plan_leg.quantity if plan_leg is not None else _f(raw.get("qty"))
        filled_qty = _f(raw.get("filled_qty")) or 0.0
        avg_price = _f(raw.get("filled_avg_price"))
        leg_status = str(raw.get("status") or "")

        if filled_qty <= 0 or avg_price is None:
            failed_legs.append(
                FailedLeg(
                    leg_symbol=symbol or "unknown",
                    reason=f"leg unfilled (broker status {leg_status or 'unknown'})",
                )
            )
            continue

        expected = plan_leg.limit_price if plan_leg is not None else None
        slippage = None if expected is None else round(avg_price - expected, 6)
        if slippage is not None:
            slippages.append(slippage)
        filled_legs.append(
            FilledLeg(
                leg_symbol=symbol,
                qty=int(round(filled_qty)),
                price=avg_price,
                filled_at=_ts(raw.get("filled_at")) or clock,
                slippage=slippage,
            )
        )
        side = plan_leg.side if plan_leg is not None else OrderSide.BUY
        sign = 1.0 if side is OrderSide.BUY else -1.0
        signed_cost += sign * avg_price * filled_qty * OPTION_MULTIPLIER

        if ordered_qty is not None and filled_qty + 1e-9 < ordered_qty:
            any_partial = True
        else:
            fully_filled += 1

    total_legs = len(raw_legs)
    parent_status = str(broker_order.get("status") or "")

    if failed_legs or any_partial:
        if filled_legs:
            status = ExecutionStatus.PARTIALLY_FILLED
        else:
            mapped = map_broker_status(parent_status)
            status = (
                mapped
                if mapped in (ExecutionStatus.CANCELLED, ExecutionStatus.FAILED)
                else ExecutionStatus.FAILED
            )
    elif fully_filled == total_legs and filled_legs:
        status = ExecutionStatus.FILLED
    else:  # no legs to speak of — defer to the broker's terminal reason
        mapped = map_broker_status(parent_status)
        status = (
            mapped
            if mapped in (ExecutionStatus.CANCELLED, ExecutionStatus.FAILED)
            else ExecutionStatus.FAILED
        )

    recovery_action = _recovery_action(status, plan, filled_legs, failed_legs)
    error = _error_message(status, broker_order, parent_status)
    actual_cost = round(abs(signed_cost), 4) if filled_legs else None
    slippage = (
        round(sum(slippages) / len(slippages), 6) if slippages else None
    )

    return ExecutionResult(
        cycle_id=plan.cycle_id,
        status=status,
        order_ids=_order_ids(broker_order, raw_legs),
        broker_order_id=str(broker_order["id"]) if broker_order.get("id") else None,
        filled_legs=filled_legs,
        failed_legs=failed_legs,
        actual_cost=actual_cost,
        slippage=slippage,
        submitted_at=_ts(broker_order.get("submitted_at")),
        completed_at=_ts(broker_order.get("filled_at"))
        or _ts(broker_order.get("updated_at"))
        or clock,
        error=error,
        recovery_action=recovery_action,
    )


def _recovery_action(
    status: ExecutionStatus,
    plan: ExecutionPlan,
    filled_legs: list[FilledLeg],
    failed_legs: list[FailedLeg],
) -> str:
    """The legging-risk recovery step for a non-clean fill (P5-BE-13)."""
    if status is not ExecutionStatus.PARTIALLY_FILLED:
        return RECOVERY_NONE
    filled_symbols = {fl.leg_symbol for fl in filled_legs}
    short_filled = any(
        occ_symbol_for_leg(leg) in filled_symbols and leg.side is OrderSide.SELL
        for leg in plan.legs
    )
    # A filled short leg with an unfilled long leg is a naked short — unwind it.
    if short_filled and failed_legs:
        return RECOVERY_UNWIND_FILLED_LEGS
    # Only long protection filled: the book is merely under-hedged — stop the rest.
    return RECOVERY_CANCEL_UNFILLED_LEGS


def _error_message(
    status: ExecutionStatus, broker_order: dict[str, Any], parent_status: str
) -> str | None:
    if status is not ExecutionStatus.FAILED:
        return None
    for key in ("reject_reason", "error", "message"):
        value = broker_order.get(key)
        if value:
            return str(value)
    return f"broker order {parent_status or 'unknown'} with no fills"


def persist_execution_result(
    engine: Engine, plan: ExecutionPlan, result: ExecutionResult
) -> OrderWithFills:
    """Write the ``orders`` row and one ``fills`` row per filled leg (P5-BE-14).

    The order status is the ``ExecutionStatus`` mapped onto the broker
    lifecycle enum (``FAILED`` → ``REJECTED``). Order + fills commit in one
    transaction via :meth:`OrderRepository.save_with_fills`.
    """
    order = OrderRecord(
        cycle_id=plan.cycle_id,
        order_class=plan.order_class,
        status=_EXECUTION_TO_ORDER_STATUS[result.status],
        legs=[leg.model_dump(mode="json") for leg in plan.legs],
        broker_order_id=result.broker_order_id,
    )
    fills = [
        FillRecord(
            order_id=0,  # rebound to the new order id inside save_with_fills
            leg_symbol=fl.leg_symbol,
            qty=Decimal(str(fl.qty)),
            price=Decimal(str(fl.price)),
            slippage=None if fl.slippage is None else Decimal(str(fl.slippage)),
        )
        for fl in result.filled_legs
    ]
    return OrderRepository(engine).save_with_fills(order, fills)
