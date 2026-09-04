"""Multi-leg option order submission via Alpaca — task **P5-BE-12** (BRD §22).

A hedge structure must reach the broker as *one* order so its legs fill together
or not at all — submitting the legs independently is the legging risk BRD §22
exists to rule out. :func:`build_mleg_order_payload` turns an
:class:`~backend.models.execution.ExecutionPlan` into a single Alpaca
``order_class: "mleg"`` combo body; :func:`submit_plan` sends it and only falls
back to independent single-leg orders when the combo is genuinely unsupported
*and* the plan opted into legging (``constraints.allow_legging``).

The OCC symbol for each leg is taken from ``leg.occ_symbol`` when the analysis
layer already resolved it, otherwise built from the leg's
``underlying / expiration / right / strike`` — the inverse of
:func:`backend.integrations.alpaca.options.parse_occ_symbol`.

Pure payload builders + a thin submit orchestrator. The only I/O is the
``submit_order`` call on the injected client, so tests pass a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import gcd
from typing import Any, Protocol

from backend.integrations.alpaca.client import AlpacaError
from backend.models.common import OptionLeg
from backend.models.enums import OptionRight, OrderSide
from backend.models.execution import ExecutionPlan

__all__ = [
    "OrderSubmitter",
    "SubmitOutcome",
    "build_mleg_order_payload",
    "build_occ_symbol",
    "build_single_leg_payloads",
    "occ_symbol_for_leg",
    "submit_plan",
]

_OCC_STRIKE_MULTIPLIER = 1000
_RIGHT_CODE = {OptionRight.CALL: "C", OptionRight.PUT: "P"}
_SIDE_WORD = {OrderSide.BUY: "buy", OrderSide.SELL: "sell"}
_OPEN_INTENT = {OrderSide.BUY: "buy_to_open", OrderSide.SELL: "sell_to_open"}

# Substrings in an Alpaca rejection that mean "this account/underlying can't do a
# combo order" — the only case a legged fallback is allowed.
_MLEG_UNSUPPORTED_MARKERS = (
    "mleg",
    "multi-leg",
    "multi leg",
    "multileg",
    "not supported",
    "unsupported",
    "not eligible",
    "not permitted",
    "not allowed",
)


class OrderSubmitter(Protocol):
    """Anything that can POST one Alpaca order body and return the order object."""

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SubmitOutcome:
    """What :func:`submit_plan` actually did.

    ``combo`` is ``True`` when a single ``mleg`` order was accepted;
    ``fell_back`` is ``True`` when the combo was rejected as unsupported and the
    legs were submitted independently instead. ``responses`` holds the broker
    order object(s) — one for a combo, one per leg for a legged submit.
    """

    responses: tuple[dict[str, Any], ...]
    submitted_payload: Any
    combo: bool
    fell_back: bool = False

    @property
    def order_ids(self) -> list[str]:
        """Broker order id(s) from the response(s), skipping any without one."""
        out: list[str] = []
        for resp in self.responses:
            oid = resp.get("id")
            if oid:
                out.append(str(oid))
        return out


def build_occ_symbol(
    underlying: str, expiration: date, right: OptionRight, strike: float
) -> str:
    """Build the 21-char OCC option id, e.g. ``AAPL251003P00145000``."""
    root = underlying.strip().upper()
    yymmdd = expiration.strftime("%y%m%d")
    strike_int = round(strike * _OCC_STRIKE_MULTIPLIER)
    return f"{root}{yymmdd}{_RIGHT_CODE[right]}{strike_int:08d}"


def occ_symbol_for_leg(leg: OptionLeg) -> str:
    """The leg's resolved ``occ_symbol`` if present, else one built from its identity."""
    if leg.occ_symbol:
        return leg.occ_symbol.strip().upper()
    return build_occ_symbol(leg.underlying, leg.expiration, leg.right, leg.strike)


def _order_type(plan: ExecutionPlan) -> str:
    otype = plan.constraints.order_type.strip().lower()
    if otype == "limit" and plan.constraints.limit_price is None:
        # A limit order with no price to set on it can only go as a market order.
        return "market"
    return otype


def build_mleg_order_payload(plan: ExecutionPlan) -> dict[str, Any]:
    """Build one Alpaca ``order_class: "mleg"`` combo body for ``plan``.

    The order ``qty`` is the GCD of the leg contract counts and each leg's
    ``ratio_qty`` is its count divided by that GCD, so a 2:1 structure submits
    as ``qty=1`` with ratios ``2`` and ``1``. A ``LIMIT`` plan with no combo
    limit price degrades to a market order rather than being sent priceless.
    """
    counts = [leg.quantity for leg in plan.legs]
    base = 0
    for count in counts:
        base = gcd(base, count)
    base = base or 1

    otype = _order_type(plan)
    payload: dict[str, Any] = {
        "order_class": "mleg",
        "qty": str(base),
        "type": otype,
        "time_in_force": plan.constraints.time_in_force.strip().lower(),
        "legs": [
            {
                "symbol": occ_symbol_for_leg(leg),
                "ratio_qty": str(leg.quantity // base),
                "side": _SIDE_WORD[leg.side],
                "position_intent": _OPEN_INTENT[leg.side],
            }
            for leg in plan.legs
        ],
    }
    if otype == "limit" and plan.constraints.limit_price is not None:
        payload["limit_price"] = str(plan.constraints.limit_price)
    return payload


def build_single_leg_payloads(plan: ExecutionPlan) -> list[dict[str, Any]]:
    """Build one independent single-leg order body per leg (the legged fallback)."""
    tif = plan.constraints.time_in_force.strip().lower()
    payloads: list[dict[str, Any]] = []
    for leg in plan.legs:
        leg_type = "limit" if leg.limit_price is not None else "market"
        body: dict[str, Any] = {
            "symbol": occ_symbol_for_leg(leg),
            "qty": str(leg.quantity),
            "side": _SIDE_WORD[leg.side],
            "type": leg_type,
            "time_in_force": tif,
            "position_intent": _OPEN_INTENT[leg.side],
        }
        if leg_type == "limit":
            body["limit_price"] = str(leg.limit_price)
        payloads.append(body)
    return payloads


def _is_mleg_unsupported(exc: AlpacaError) -> bool:
    text = str(exc).lower()
    if "mleg" in text or "combo" in text or "multi" in text:
        return True
    return any(marker in text for marker in _MLEG_UNSUPPORTED_MARKERS)


def submit_plan(
    client: OrderSubmitter,
    plan: ExecutionPlan,
    *,
    allow_legging: bool | None = None,
) -> SubmitOutcome:
    """Submit ``plan`` as one combo order, legging in only if forced to.

    A single-leg plan goes as one plain order. A multi-leg plan goes as one
    ``mleg`` combo; if the broker rejects that as unsupported **and** legging is
    permitted (``allow_legging`` arg, else ``plan.constraints.allow_legging``),
    each leg is then submitted independently. Any other broker error propagates.
    """
    legging_ok = (
        plan.constraints.allow_legging if allow_legging is None else allow_legging
    )

    if len(plan.legs) == 1:
        payload = build_single_leg_payloads(plan)[0]
        return SubmitOutcome(
            responses=(client.submit_order(payload),),
            submitted_payload=payload,
            combo=False,
        )

    combo_payload = build_mleg_order_payload(plan)
    try:
        response = client.submit_order(combo_payload)
    except AlpacaError as exc:
        if not (legging_ok and _is_mleg_unsupported(exc)):
            raise
        leg_payloads = build_single_leg_payloads(plan)
        responses = tuple(client.submit_order(p) for p in leg_payloads)
        return SubmitOutcome(
            responses=responses,
            submitted_payload=leg_payloads,
            combo=False,
            fell_back=True,
        )

    return SubmitOutcome(
        responses=(response,),
        submitted_payload=combo_payload,
        combo=True,
    )
