"""Collar agent tests — task P4-BE-4 (BRD §15–16).

Long put + short OTM call; net cost near zero or a credit; the call strike is
recorded as the upside cap. NOT_VIABLE when there is no put or no call to build
the structure from.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.strategies import CollarAgent
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_PUTS = (("2026-10-03", 90.0, 2.50),)
_CALLS = (("2026-10-03", 110.0, 2.30), ("2026-10-03", 115.0, 1.40))


def _context(
    *,
    budget_pct: float = 0.05,
    puts: tuple[tuple[str, float, float], ...] = _PUTS,
    calls: tuple[tuple[str, float, float], ...] = _CALLS,
) -> HedgeContext:
    def _rows(rows, right):
        return [
            {
                "underlying": "XYZ",
                "right": right,
                "strike": strike,
                "expiration": expiration,
                "premium": premium,
                "open_interest": 2_000,
                "iv": 0.25,
                "liquidity": "high",
            }
            for expiration, strike, premium in rows
        ]

    return HedgeContext.model_validate(
        {
            "cycle_id": "cyc-p4-be-4",
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [
                    {
                        "symbol": "XYZ",
                        "qty": 100.0,
                        "avg_price": 80.0,
                        "market_value": 10_000.0,
                    }
                ],
                "volatility": 0.28,
            },
            "objective": {
                "max_hedge_budget_pct": budget_pct,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": _rows(puts, "PUT") + _rows(calls, "CALL"),
        }
    )


def test_long_put_short_call_for_a_small_net_debit() -> None:
    hyp = CollarAgent().propose(_context())

    assert hyp.viable is True
    assert hyp.strategy is StrategyType.COLLAR
    assert hyp.action is HedgeAction.NEW_HEDGE

    put_leg, call_leg = hyp.legs
    assert (put_leg.right, put_leg.side, put_leg.strike) == (
        OptionRight.PUT,
        OrderSide.BUY,
        90.0,
    )
    # the 110 call premium (2.30) offsets the 2.50 put better than the 115 (1.40)
    assert (call_leg.right, call_leg.side, call_leg.strike) == (
        OptionRight.CALL,
        OrderSide.SELL,
        110.0,
    )
    # net = (2.50 - 2.30) * 1 * 100 = 20
    assert hyp.cost == pytest.approx(20.0)
    assert hyp.hedge_metrics.max_loss == pytest.approx(1_020.0)
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_call_cap_is_recorded_in_the_tradeoffs() -> None:
    hyp = CollarAgent().propose(_context())

    assert any("110" in tradeoff for tradeoff in hyp.tradeoffs)
    assert "110" in hyp.rationale


def test_collar_can_be_a_net_credit() -> None:
    hyp = CollarAgent().propose(
        _context(
            calls=(("2026-10-03", 110.0, 2.80), ("2026-10-03", 115.0, 1.40))
        )
    )

    # net = (2.50 - 2.80) * 100 = -30 → cost clamps to 0, credit shown in prose
    assert hyp.viable is True
    assert hyp.cost == 0.0
    assert hyp.hedge_metrics.cost_pct_of_portfolio == 0.0
    assert "credit" in hyp.rationale.lower()


def test_greeks_net_a_long_put_and_a_short_call() -> None:
    metrics = CollarAgent().propose(_context()).hedge_metrics

    # long put (delta < 0) + short call (delta < 0) → net short delta
    assert metrics.net_delta < 0
    # long a put, short a call: net short gamma / vega, net long theta
    assert metrics.net_gamma < 0
    assert metrics.net_vega < 0
    assert metrics.net_theta > 0


def test_zero_total_value_does_not_raise_on_a_zero_cost_collar() -> None:
    # a net-zero collar (put 2.00 / call 2.00) on a degenerate total_value=0
    # book: cost clamps to 0 and the cost-of-portfolio metric stays defined
    # rather than dividing 0 by 0.
    ctx = _context(
        puts=(("2026-10-03", 90.0, 2.00),),
        calls=(("2026-10-03", 110.0, 2.00), ("2026-10-03", 115.0, 1.40)),
    )
    broke = ctx.model_copy(
        update={
            "portfolio_state": ctx.portfolio_state.model_copy(
                update={"total_value": 0.0}
            )
        }
    )

    hyp = CollarAgent().propose(broke)  # must not raise ZeroDivisionError

    assert hyp.viable is True
    assert hyp.cost == 0.0
    assert hyp.hedge_metrics.cost_pct_of_portfolio == 0.0
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_no_call_to_finance_the_collar_is_not_viable() -> None:
    hyp = CollarAgent().propose(_context(calls=()))

    assert hyp.viable is False
    assert hyp.strategy is StrategyType.COLLAR
    assert "call" in hyp.rejection_reason.lower()


def test_no_put_is_not_viable() -> None:
    hyp = CollarAgent().propose(_context(puts=()))

    assert hyp.viable is False
    assert "put" in hyp.rejection_reason.lower()
