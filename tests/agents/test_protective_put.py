"""Protective Put agent tests — task P4-BE-2 (BRD §15–16).

The agent picks a strike near the drawdown tolerance and sizes one put per 100
covered shares; ``cost``, the payoff floor and the Greeks all come from
``backend.quant``. An over-budget context is a first-class NOT_VIABLE, not an
exception. The final case runs it on the recorded seed context and hand-checks
the floor and cost.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.agents.strategies import ProtectivePutAgent
from backend.agents.strategies._common import RISK_FREE_RATE
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis
from backend.quant.greeks import black_scholes

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)
_DEFAULT_PUTS = (
    ("2026-10-03", 95.0, 3.50),
    ("2026-10-03", 90.0, 2.00),
    ("2026-10-03", 85.0, 1.20),
)


def _context(
    *,
    budget_pct: float = 0.05,
    tolerance: float = 0.10,
    puts: tuple[tuple[str, float, float], ...] = _DEFAULT_PUTS,
    shares: float = 100.0,
    spot: float = 100.0,
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
            "cycle_id": "cyc-p4-be-2",
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [
                    {
                        "symbol": "XYZ",
                        "qty": shares,
                        "avg_price": 80.0,
                        "market_value": spot * shares,
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


def test_picks_the_strike_near_tolerance_and_sizes_to_the_holding() -> None:
    hyp = ProtectivePutAgent().propose(_context())

    assert hyp.viable is True
    assert hyp.strategy is StrategyType.PROTECTIVE_PUT
    assert hyp.action is HedgeAction.NEW_HEDGE
    # target strike = spot 100 * (1 - 0.10) = 90 → the 90 put, 1 contract / 100 sh
    assert [leg.strike for leg in hyp.legs] == [90.0]
    assert hyp.legs[0].quantity == 1
    # cost = premium 2.00 * 1 contract * 100 multiplier
    assert hyp.cost == pytest.approx(200.0)
    assert hyp.hedge_metrics.cost_pct_of_portfolio == pytest.approx(0.002)
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_sizes_one_contract_per_hundred_covered_shares() -> None:
    # 250 shares → 2 whole contracts (the trailing 50 are left uncovered)
    hyp = ProtectivePutAgent().propose(_context(shares=250.0, spot=100.0))

    assert hyp.legs[0].quantity == 2
    # cost = premium 2.00 * 2 contracts * 100
    assert hyp.cost == pytest.approx(400.0)
    # 2 * 100 * spot 100 = 20_000 hedged vs 25_000 exposure
    assert hyp.hedge_metrics.hedge_ratio == pytest.approx(0.8)


def test_payoff_floor_and_cost_match_a_hand_check() -> None:
    hyp = ProtectivePutAgent().propose(_context())

    # 100 shares entered at 100 + long 1x 90 put at 2.00: below 90 the put
    # offsets the stock 1:1, so the worst P&L is 100*(90-100) - 200 = -1_200
    # and the covered value floors at 10_000 - 1_200 = 8_800.
    assert hyp.hedge_metrics.max_loss == pytest.approx(1_200.0)
    assert min(p.pnl for p in hyp.payoff_profile) == pytest.approx(-1_200.0)
    assert hyp.hedge_metrics.downside_protection_pct == pytest.approx(0.9)
    # 1 contract * 100 * spot 100 = 10_000 hedged vs 10_000 exposure
    assert hyp.hedge_metrics.hedge_ratio == pytest.approx(1.0)


def test_greeks_are_the_black_scholes_values_scaled_to_contracts() -> None:
    hyp = ProtectivePutAgent().propose(_context())
    metrics = hyp.hedge_metrics

    # a long put: short delta, long gamma / vega, short theta
    assert metrics.net_delta < 0
    assert metrics.net_gamma > 0
    assert metrics.net_vega > 0
    assert metrics.net_theta < 0

    greeks = black_scholes(100.0, 90.0, 30 / 365.0, 0.25, RISK_FREE_RATE, "PUT")
    assert metrics.net_delta == pytest.approx(greeks.delta * 100.0)
    assert metrics.net_gamma == pytest.approx(greeks.gamma * 100.0)
    assert metrics.net_vega == pytest.approx(greeks.vega * 100.0)
    assert metrics.net_theta == pytest.approx(greeks.theta * 100.0)


def test_over_budget_context_is_not_viable_not_an_exception() -> None:
    # budget = 0.001 * 100_000 = 100, under the 200 premium
    hyp = ProtectivePutAgent().propose(_context(budget_pct=0.001))

    assert hyp.viable is False
    assert hyp.strategy is StrategyType.PROTECTIVE_PUT
    assert hyp.action is HedgeAction.NO_TRADE
    assert "budget" in hyp.rejection_reason.lower()
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_no_put_on_the_name_is_not_viable() -> None:
    hyp = ProtectivePutAgent().propose(_context(puts=()))

    assert hyp.viable is False
    assert "put" in hyp.rejection_reason.lower()


def test_empty_book_is_not_viable() -> None:
    ctx = _context()
    bare = ctx.model_copy(
        update={
            "portfolio_state": ctx.portfolio_state.model_copy(
                update={"positions": []}
            )
        }
    )
    hyp = ProtectivePutAgent().propose(bare)

    assert hyp.viable is False
    assert "holding" in hyp.rejection_reason.lower()


def test_runs_on_the_seed_context() -> None:
    ctx = HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))

    hyp = ProtectivePutAgent().propose(ctx)

    assert hyp.viable is True
    # AAPL is the largest holding (mv 22_500, 100 sh → spot 225); the nearest
    # put to 225 * 0.9 = 202.5 among {145, 140} is 145 @ 3.15.
    assert hyp.legs[0].underlying == "AAPL"
    assert hyp.legs[0].strike == 145.0
    assert hyp.cost == pytest.approx(315.0)
    # below 145 the put offsets 1:1 → worst = 100*(145-225) - 315 = -8_315
    assert hyp.hedge_metrics.max_loss == pytest.approx(8_315.0)
    assert min(p.pnl for p in hyp.payoff_profile) == pytest.approx(-8_315.0)
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp
