"""Alpaca multi-leg order submission — task P5-BE-12 / issue #135.

Offline: an :class:`~backend.models.execution.ExecutionPlan` becomes **one**
``order_class: "mleg"`` combo payload; :func:`submit_plan` only legs in
independently when the broker rejects the combo as unsupported *and* the plan
allowed legging.

Smoke (``-m smoke``, needs live paper creds): submit a real 2-leg SPY put
spread and confirm Alpaca returns one combo order.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

from backend.integrations.alpaca import build_occ_symbol
from backend.integrations.alpaca.client import AlpacaError
from backend.integrations.alpaca.orders import (
    build_mleg_order_payload,
    build_single_leg_payloads,
    submit_plan,
)
from backend.models.enums import OptionRight
from backend.models.execution import ExecutionPlan


def _plan(**overrides: Any) -> ExecutionPlan:
    raw: dict[str, Any] = {
        "cycle_id": "cyc-submit",
        "approval_id": "risk-cyc-submit",
        "strategy": "PUT_SPREAD",
        "legs": [
            {
                "underlying": "AAPL",
                "right": "PUT",
                "side": "BUY",
                "strike": 145.0,
                "expiration": "2026-10-03",
                "quantity": 2,
                "limit_price": 3.15,
            },
            {
                "underlying": "AAPL",
                "right": "PUT",
                "side": "SELL",
                "strike": 140.0,
                "expiration": "2026-10-03",
                "quantity": 2,
                "limit_price": 1.95,
            },
        ],
        "order_class": "MLEG",
        "constraints": {"limit_price": 1.2, "allow_legging": False},
        "estimated_cost": 240.0,
    }
    raw.update(overrides)
    return ExecutionPlan.model_validate(raw)


class _FakeBroker:
    """Records every ``submit_order`` payload; scripted to accept or reject."""

    def __init__(self, *, reject_mleg: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reject_mleg = reject_mleg
        self._n = 0

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        if payload.get("order_class") == "mleg" and self._reject_mleg:
            raise AlpacaError(self._reject_mleg)
        self._n += 1
        return {"id": f"ord-{self._n}", "status": "accepted", "symbol": payload.get("symbol")}


def test_build_occ_symbol_matches_occ_format() -> None:
    assert (
        build_occ_symbol("AAPL", date(2026, 10, 3), OptionRight.PUT, 145.0)
        == "AAPL261003P00145000"
    )


def test_plan_becomes_one_multi_leg_payload() -> None:
    payload = build_mleg_order_payload(_plan())

    assert payload["order_class"] == "mleg"
    assert payload["type"] == "limit"
    assert payload["limit_price"] == "1.2"
    assert payload["qty"] == "2"  # gcd(2, 2)
    assert [(leg["symbol"], leg["side"], leg["ratio_qty"]) for leg in payload["legs"]] == [
        ("AAPL261003P00145000", "buy", "1"),
        ("AAPL261003P00140000", "sell", "1"),
    ]


def test_ratio_qty_uses_gcd_of_leg_counts() -> None:
    plan = _plan(
        legs=[
            {**_plan().legs[0].model_dump(mode="json"), "quantity": 40},
            {**_plan().legs[1].model_dump(mode="json"), "quantity": 20},
        ]
    )
    payload = build_mleg_order_payload(plan)
    assert payload["qty"] == "20"
    assert [leg["ratio_qty"] for leg in payload["legs"]] == ["2", "1"]


def test_submit_plan_sends_a_single_combo_order() -> None:
    broker = _FakeBroker()
    outcome = submit_plan(broker, _plan())

    assert outcome.combo is True
    assert outcome.fell_back is False
    assert len(broker.calls) == 1
    assert broker.calls[0]["order_class"] == "mleg"
    assert outcome.order_ids == ["ord-1"]


def test_submit_plan_legs_in_only_when_combo_unsupported_and_allowed() -> None:
    broker = _FakeBroker(reject_mleg="mleg orders are not supported for this account")
    outcome = submit_plan(broker, _plan(constraints={"limit_price": 1.2, "allow_legging": True}))

    assert outcome.combo is False
    assert outcome.fell_back is True
    # one rejected combo attempt + one order per leg
    assert len(broker.calls) == 3
    assert broker.calls[0]["order_class"] == "mleg"
    assert [c["symbol"] for c in broker.calls[1:]] == [
        "AAPL261003P00145000",
        "AAPL261003P00140000",
    ]
    assert len(outcome.responses) == 2


def test_submit_plan_does_not_leg_in_when_legging_disallowed() -> None:
    broker = _FakeBroker(reject_mleg="mleg not supported")
    with pytest.raises(AlpacaError):
        submit_plan(broker, _plan(constraints={"limit_price": 1.2, "allow_legging": False}))
    assert len(broker.calls) == 1  # no legged retry


def test_submit_plan_propagates_unrelated_broker_errors() -> None:
    broker = _FakeBroker(reject_mleg="insufficient buying power")
    with pytest.raises(AlpacaError):
        submit_plan(broker, _plan(constraints={"limit_price": 1.2, "allow_legging": True}))
    assert len(broker.calls) == 1  # not a combo-support problem — do not leg in


def test_single_leg_plan_submits_one_plain_order() -> None:
    broker = _FakeBroker()
    plan = _plan(
        legs=[_plan().legs[0].model_dump(mode="json")],
        order_class="SINGLE",
        constraints={"allow_legging": False},
    )
    outcome = submit_plan(broker, plan)

    assert outcome.combo is False
    assert outcome.fell_back is False
    assert len(broker.calls) == 1
    assert "order_class" not in broker.calls[0]
    assert broker.calls[0]["symbol"] == "AAPL261003P00145000"


# --------------------------------------------------------------------------- #
# smoke — real paper account
# --------------------------------------------------------------------------- #


@pytest.mark.smoke
def test_smoke_submits_two_leg_paper_combo() -> None:
    """`pytest -m smoke` — a real 2-leg SPY put spread lands as one combo order."""
    if not (os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")):
        pytest.skip("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")

    from backend.integrations.alpaca.client import AlpacaClient
    from backend.integrations.alpaca.options import OptionChainClient

    with OptionChainClient() as chain_client:
        chain = chain_client.get_chain("SPY", right="put")
    assert chain, "no SPY put chain returned"

    # pick a near expiry with at least two strikes and build a debit spread
    by_expiry: dict[date, list[Any]] = {}
    for contract in chain:
        by_expiry.setdefault(contract.expiry, []).append(contract)
    expiry, strikes = next(
        (exp, sorted(cs, key=lambda c: c.strike))
        for exp, cs in sorted(by_expiry.items())
        if len(cs) >= 2
    )
    long_leg, short_leg = strikes[len(strikes) // 2], strikes[len(strikes) // 2 - 1]

    plan = ExecutionPlan.model_validate(
        {
            "cycle_id": "smoke-submit",
            "approval_id": "smoke",
            "strategy": "PUT_SPREAD",
            "legs": [
                {
                    "underlying": "SPY",
                    "right": "PUT",
                    "side": "BUY",
                    "strike": long_leg.strike,
                    "expiration": expiry.isoformat(),
                    "quantity": 1,
                    "occ_symbol": long_leg.symbol,
                },
                {
                    "underlying": "SPY",
                    "right": "PUT",
                    "side": "SELL",
                    "strike": short_leg.strike,
                    "expiration": expiry.isoformat(),
                    "quantity": 1,
                    "occ_symbol": short_leg.symbol,
                },
            ],
            "order_class": "MLEG",
            "constraints": {"order_type": "MARKET", "allow_legging": False},
            "estimated_cost": 0.0,
        }
    )

    outcome = submit_plan(AlpacaClient(), plan)
    assert outcome.combo is True
    assert outcome.order_ids, "Alpaca returned no order id for the combo"
