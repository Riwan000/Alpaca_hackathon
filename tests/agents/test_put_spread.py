"""Put Spread agent tests — task P4-BE-3 (BRD §15–16).

Long strike above short strike; the structure's ``max_loss`` equals the net
debit; NOT_VIABLE when there is no strike to sell below the long strike or the
debit is over budget. Legs and the net debit reconcile with ``quant/payoff``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.strategies import PutSpreadAgent
from backend.models.enums import HedgeAction, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis
from backend.quant.payoff import PayoffLeg, structure_risk

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_DEFAULT_PUTS = (
    ("2026-10-03", 95.0, 3.00),
    ("2026-10-03", 90.0, 1.80),
    ("2026-10-03", 85.0, 1.00),
)


def _context(
    *,
    budget_pct: float = 0.05,
    tolerance: float = 0.10,
    puts: tuple[tuple[str, float, float], ...] = _DEFAULT_PUTS,
) -> HedgeContext:
    candidates = [
        {
            "underlying": "XYZ",
            "right": "PUT",
            "strike": strike,
            "expiration": expiration,
            "premium": premium,
            "open_interest": 2_000,
            "iv": 0.25,
            "liquidity": "high",
        }
        for expiration, strike, premium in puts
    ]
    return HedgeContext.model_validate(
        {
            "cycle_id": "cyc-p4-be-3",
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
                "drawdown_tolerance_pct": tolerance,
            },
            "option_candidates": candidates,
        }
    )


def test_long_strike_above_short_strike_and_debit_matches_quant() -> None:
    hyp = PutSpreadAgent().propose(_context())

    assert hyp.viable is True
    assert hyp.strategy is StrategyType.PUT_SPREAD
    assert hyp.action is HedgeAction.NEW_HEDGE

    long_leg, short_leg = hyp.legs
    assert long_leg.side is OrderSide.BUY
    assert short_leg.side is OrderSide.SELL
    assert long_leg.strike == 90.0
    assert short_leg.strike == 85.0
    assert long_leg.strike > short_leg.strike

    # net debit = (1.80 - 1.00) * 1 contract * 100 = 80
    assert hyp.cost == pytest.approx(80.0)
    reconciled = structure_risk(
        [
            PayoffLeg(kind="PUT", quantity=1, strike=90.0, premium=1.80, multiplier=100.0),
            PayoffLeg(kind="PUT", quantity=-1, strike=85.0, premium=1.00, multiplier=100.0),
        ]
    )
    assert hyp.cost == pytest.approx(-reconciled.worst_pnl)
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_max_loss_equals_the_net_debit() -> None:
    hyp = PutSpreadAgent().propose(_context())

    assert hyp.hedge_metrics.max_loss == pytest.approx(hyp.cost)
    assert hyp.hedge_metrics.max_loss == pytest.approx(80.0)
    # breakeven = long strike - debit/100 = 90 - 0.80 = 89.20
    assert hyp.hedge_metrics.breakevens[0] == pytest.approx(89.20)


def test_greeks_net_a_long_and_a_short_put() -> None:
    hyp = PutSpreadAgent().propose(_context())
    metrics = hyp.hedge_metrics

    # long the richer 90 put, short the 85 put: net still long gamma / vega
    assert metrics.net_gamma > 0
    assert metrics.net_vega > 0
    assert metrics.net_delta < 0


def test_no_lower_strike_to_sell_is_not_viable() -> None:
    hyp = PutSpreadAgent().propose(
        _context(puts=(("2026-10-03", 90.0, 1.80), ("2026-10-03", 95.0, 3.00)))
    )

    assert hyp.viable is False
    assert hyp.strategy is StrategyType.PUT_SPREAD
    assert "finance" in hyp.rejection_reason.lower()


def test_a_single_strike_cannot_form_a_spread() -> None:
    hyp = PutSpreadAgent().propose(_context(puts=(("2026-10-03", 90.0, 1.80),)))

    assert hyp.viable is False
    assert "two put strikes" in hyp.rejection_reason.lower()


def test_spread_over_budget_is_not_viable() -> None:
    # budget = 0.0005 * 100_000 = 50, under the 80 debit
    hyp = PutSpreadAgent().propose(_context(budget_pct=0.0005))

    assert hyp.viable is False
    assert "budget" in hyp.rejection_reason.lower()
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp
