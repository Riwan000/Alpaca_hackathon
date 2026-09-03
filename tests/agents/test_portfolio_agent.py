"""Portfolio Analysis Agent tests — task P3-BE-5 (BRD §12).

The agent's output must validate as the ``HedgeContext`` portfolio slice and its
numbers must come from ``backend.quant`` — never the LLM. Exposure and drawdown
are pinned against a hand calculation on the seed book.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs, build_agent_contexts
from backend.agents.portfolio import analyze_portfolio
from backend.models.hedge_context import PortfolioState
from backend.quant.helpers import returns_from_prices
from backend.quant.risk import volatility as quant_volatility

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)

# seed book — four long equity holdings, gross == net == 75_000
_POSITIONS = [
    {"symbol": "AAPL", "qty": 100.0, "avg_price": 210.0, "market_value": 22_500.0},
    {"symbol": "NVDA", "qty": 150.0, "avg_price": 115.0, "market_value": 18_000.0},
    {"symbol": "MSFT", "qty": 50.0, "avg_price": 400.0, "market_value": 20_500.0},
    {"symbol": "SPY", "qty": 25.0, "avg_price": 540.0, "market_value": 14_000.0},
]
_EQUITY_CURVE = [100_000.0, 105_000.0, 102_000.0, 108_000.0, 99_000.0, 103_000.0]


def _inputs(*, equity_curve: list[float] | None = None) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-5",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 175_000.0,
                "cash": 100_000.0,
                "equity": 75_000.0,
                "buying_power": 50_000.0,
                "positions": _POSITIONS,
                # deliberately wrong placeholders — the agent must overwrite them
                "gross_exposure": 1.0,
                "net_exposure": 1.0,
                "concentration_hhi": 0.999,
                "drawdown": -0.5,
                "max_drawdown": -0.5,
                "volatility": 9.9,
                "beta": 1.23,
            },
            "equity_curve": equity_curve or [],
        }
    )


def _run(inputs: AnalysisInputs, client=None) -> PortfolioState:
    ctx = build_agent_contexts(inputs)["portfolio"]
    return analyze_portfolio(ctx, client=client)


def test_output_is_a_portfolio_state_that_round_trips() -> None:
    out = _run(_inputs(equity_curve=_EQUITY_CURVE))
    assert isinstance(out, PortfolioState)
    PortfolioState.model_validate(out.model_dump())


def test_exposure_matches_hand_check() -> None:
    out = _run(_inputs())
    # long-only book: gross == net == Σ market_value
    assert out.gross_exposure == pytest.approx(75_000.0)
    assert out.net_exposure == pytest.approx(75_000.0)


def test_concentration_hhi_matches_hand_check() -> None:
    out = _run(_inputs())
    weights = [22_500, 18_000, 20_500, 14_000]
    expected = sum((w / 75_000) ** 2 for w in weights)
    assert out.concentration_hhi == pytest.approx(expected)
    assert 0.0 <= out.concentration_hhi <= 1.0


def test_drawdown_matches_hand_check_on_the_equity_curve() -> None:
    out = _run(_inputs(equity_curve=_EQUITY_CURVE))
    # peak 108_000 → trough 99_000 → recovers to 103_000
    assert out.drawdown == pytest.approx((103_000 - 108_000) / 108_000)
    assert out.max_drawdown == pytest.approx((99_000 - 108_000) / 108_000 * -1)
    assert out.max_drawdown >= 0.0
    assert out.drawdown <= 0.0


def test_volatility_comes_from_quant_not_the_llm(mock_llm) -> None:
    out = _run(_inputs(equity_curve=_EQUITY_CURVE), client=mock_llm)
    expected = quant_volatility(returns_from_prices(_EQUITY_CURVE)).annualized
    assert out.volatility == pytest.approx(expected)
    assert mock_llm.calls == []  # the Portfolio agent never calls the model


@pytest.mark.parametrize("curve", [[100_000.0, 101_000.0], [100_000.0, 99_000.0]])
def test_two_point_curve_gives_drawdown_but_no_volatility_crash(curve) -> None:
    out = _run(_inputs(equity_curve=curve))
    # drawdown works at 2 points; volatility needs ≥ 3 → snapshot value kept
    assert out.max_drawdown >= 0.0
    assert out.volatility == 9.9


def test_three_point_curve_is_the_shortest_that_yields_volatility() -> None:
    out = _run(_inputs(equity_curve=[100_000.0, 110_000.0, 99_000.0]))
    expected = quant_volatility(returns_from_prices([100_000.0, 110_000.0, 99_000.0])).annualized
    assert out.volatility == pytest.approx(expected)


def test_metrics_pass_through_when_no_equity_curve_is_supplied() -> None:
    out = _run(_inputs(equity_curve=[]))
    # exposure/HHI are always recomputed; drawdown/vol/beta keep the snapshot value
    assert out.drawdown == -0.5
    assert out.max_drawdown == -0.5
    assert out.volatility == 9.9
    assert out.beta == 1.23


def test_short_leg_reduces_net_exposure() -> None:
    inputs = _inputs()
    raw = inputs.model_dump(mode="json")
    raw["portfolio_state"]["positions"].append(
        {
            "symbol": "TSLA",
            "qty": 40.0,
            "avg_price": 250.0,
            "market_value": 10_000.0,
            "side": "SELL",
        }
    )
    out = _run(AnalysisInputs.model_validate(raw))
    assert out.gross_exposure == pytest.approx(85_000.0)
    assert out.net_exposure == pytest.approx(65_000.0)
