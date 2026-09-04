"""Execution Agent — build an :class:`ExecutionPlan` from an approved decision.

Task **P5-BE-10** (BRD §21). The risk gate hands execution a
:class:`~backend.models.risk.RiskDecision` whose verdict is ``APPROVE`` or
``MODIFY``. :func:`build_execution_plan` turns that into a ready-to-submit
:class:`~backend.models.execution.ExecutionPlan`:

* legs come straight from ``decision.approved_hypothesis`` — same underlyings,
  strikes, expiries, sides and quantities;
* every ``MODIFY`` adjustment in ``decision.modifications`` is applied to the
  legs / order constraints before the plan is built, so a risk-mandated size
  cut or price tightening is never silently dropped;
* ``order_class`` is ``MLEG`` for a multi-leg structure (combo submission, no
  legging risk — BRD §22) and ``SINGLE`` for a lone leg;
* ``estimated_cost`` is the hypothesis cost, scaled pro-rata when a quantity
  modification resized the structure.

Pure function. No LLM, no I/O. A ``REJECT`` decision, or one with no approved
hypothesis, raises :class:`ExecutionPlanError` — there is nothing to execute.
"""

from __future__ import annotations

import re

from backend.models.common import OptionLeg
from backend.models.enums import OrderSide, RiskVerdict
from backend.models.execution import ExecutionPlan, OrderConstraints
from backend.models.risk import RiskDecision, RiskModification

__all__ = ["ExecutionPlanError", "build_execution_plan"]

_MLEG = "MLEG"
_SINGLE = "SINGLE"

# ``legs[<index>].<field>`` — a modification targeting one leg.
_LEG_FIELD_RE = re.compile(r"^legs\[(\d+)\]\.(quantity|limit_price)$")

# Order-level modification fields the agent knows how to apply.
_FIELD_QUANTITY = "quantity"
_FIELD_LIMIT_PRICE = "limit_price"
_FIELD_PRICE_TOLERANCE = "price_tolerance_pct"
_FIELD_ALLOW_LEGGING = "allow_legging"


class ExecutionPlanError(ValueError):
    """The approved decision cannot be turned into an executable plan."""


def build_execution_plan(
    decision: RiskDecision,
    *,
    approval_id: str,
    price_tolerance_pct: float | None = None,
) -> ExecutionPlan:
    """Build the :class:`ExecutionPlan` for an ``APPROVE`` / ``MODIFY`` decision.

    Args:
        decision: the risk-gate output. ``verdict`` must be ``APPROVE`` or
            ``MODIFY`` and ``approved_hypothesis`` must be set.
        approval_id: id of the risk evaluation that cleared this plan (the
            persisted ``risk_checks`` row id, or a synthetic ``risk-<cycle>``).
        price_tolerance_pct: overrides the plan's pre-flight price band; falls
            back to the :class:`OrderConstraints` default when ``None``.

    Returns:
        A validated :class:`ExecutionPlan` whose legs and quantities match the
        approved hypothesis with every ``MODIFY`` adjustment applied.

    Raises:
        ExecutionPlanError: the verdict is ``REJECT``, no hypothesis was
            approved, or a modification names a field the agent cannot apply.
    """
    if decision.verdict is RiskVerdict.REJECT:
        raise ExecutionPlanError(
            f"cannot build a plan for a REJECT decision (cycle {decision.cycle_id})"
        )
    hypothesis = decision.approved_hypothesis
    if hypothesis is None:
        raise ExecutionPlanError(
            f"decision for cycle {decision.cycle_id} carries no approved_hypothesis"
        )
    if not hypothesis.legs:
        raise ExecutionPlanError(
            f"approved hypothesis for cycle {decision.cycle_id} has no legs to execute"
        )

    legs = [leg.model_copy() for leg in hypothesis.legs]
    constraints_kwargs: dict[str, object] = {}
    if price_tolerance_pct is not None:
        constraints_kwargs["price_tolerance_pct"] = price_tolerance_pct

    for mod in decision.modifications:
        legs, constraints_kwargs = _apply_modification(
            mod, legs, constraints_kwargs, decision.cycle_id
        )

    original_contracts = sum(leg.quantity for leg in hypothesis.legs)
    new_contracts = sum(leg.quantity for leg in legs)
    scale = new_contracts / original_contracts if original_contracts else 1.0
    estimated_cost = round(max(0.0, hypothesis.cost * scale), 4)

    constraints_kwargs.setdefault("limit_price", _net_combo_limit(legs))
    constraints = OrderConstraints(**constraints_kwargs)

    order_class = _MLEG if len(legs) > 1 else _SINGLE
    return ExecutionPlan(
        cycle_id=decision.cycle_id,
        approval_id=approval_id,
        strategy=hypothesis.strategy,
        legs=legs,
        order_class=order_class,
        constraints=constraints,
        estimated_cost=estimated_cost,
    )


def _apply_modification(
    mod: RiskModification,
    legs: list[OptionLeg],
    constraints_kwargs: dict[str, object],
    cycle_id: str,
) -> tuple[list[OptionLeg], dict[str, object]]:
    """Apply one :class:`RiskModification` to the legs / constraints in place."""
    leg_match = _LEG_FIELD_RE.match(mod.field)
    if leg_match is not None:
        index, field = int(leg_match.group(1)), leg_match.group(2)
        if index >= len(legs):
            raise ExecutionPlanError(
                f"modification targets legs[{index}] but the plan has {len(legs)} leg(s)"
            )
        if field == _FIELD_QUANTITY:
            legs[index] = legs[index].model_copy(
                update={"quantity": _as_positive_int(mod, "leg quantity")}
            )
        else:  # limit_price
            legs[index] = legs[index].model_copy(
                update={"limit_price": _as_non_negative_float(mod, "leg limit_price")}
            )
        return legs, constraints_kwargs

    if mod.field == _FIELD_QUANTITY:
        qty = _as_positive_int(mod, "quantity")
        legs = [leg.model_copy(update={"quantity": qty}) for leg in legs]
        return legs, constraints_kwargs

    if mod.field == _FIELD_LIMIT_PRICE:
        constraints_kwargs["limit_price"] = _as_non_negative_float(mod, "limit_price")
        return legs, constraints_kwargs

    if mod.field == _FIELD_PRICE_TOLERANCE:
        constraints_kwargs["price_tolerance_pct"] = _as_non_negative_float(
            mod, "price_tolerance_pct"
        )
        return legs, constraints_kwargs

    if mod.field == _FIELD_ALLOW_LEGGING:
        constraints_kwargs["allow_legging"] = _as_bool(mod.to_value)
        return legs, constraints_kwargs

    raise ExecutionPlanError(
        f"cycle {cycle_id}: risk modification names an unsupported field "
        f"{mod.field!r} — refusing to drop it silently"
    )


def _net_combo_limit(legs: list[OptionLeg]) -> float | None:
    """Net per-combo debit from the leg limit prices, or ``None``.

    ``Σ (+limit_price for a BUY leg, -limit_price for a SELL leg)``. Returns
    ``None`` unless every leg carries a limit price and the net is a debit
    (``> 0``) — a net credit has no non-negative limit to set.
    """
    if any(leg.limit_price is None for leg in legs):
        return None
    net = sum(
        (leg.limit_price or 0.0) * (1.0 if leg.side is OrderSide.BUY else -1.0)
        for leg in legs
    )
    return round(net, 4) if net > 0 else None


def _as_positive_int(mod: RiskModification, label: str) -> int:
    try:
        value = int(float(mod.to_value))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ExecutionPlanError(
            f"modification {mod.field!r}: {label} to_value {mod.to_value!r} is not a number"
        ) from exc
    if value <= 0:
        raise ExecutionPlanError(
            f"modification {mod.field!r}: {label} must be positive, got {value}"
        )
    return value


def _as_non_negative_float(mod: RiskModification, label: str) -> float:
    try:
        value = float(mod.to_value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ExecutionPlanError(
            f"modification {mod.field!r}: {label} to_value {mod.to_value!r} is not a number"
        ) from exc
    if value < 0:
        raise ExecutionPlanError(
            f"modification {mod.field!r}: {label} must be non-negative, got {value}"
        )
    return value


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False
