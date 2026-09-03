"""Market Analysis Agent tests — task P3-BE-7 (BRD §13).

``regime`` is always one of the ``MarketRegime`` tokens; index trend / VIX are
carried straight from the P3-BE-1 market data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs, build_agent_contexts
from backend.agents.market import analyze_market
from backend.models.enums import MarketRegime
from backend.models.hedge_context import MarketState

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_REGIMES = {r.value for r in MarketRegime}


def _inputs(*, index_trend: str = "DOWN", vix: float = 24.5) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-7",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [],
            },
            "market_data": {
                "index_symbol": "SPY",
                "index_trend": index_trend,
                "index_price": 498.2,
                "vix": vix,
                "sector_trends": {"tech": "DOWN", "energy": "UP"},
                "macro_notes": ["Fed on hold", "credit spreads widening"],
                "as_of": _NOW.isoformat(),
            },
        }
    )


def _run(inputs: AnalysisInputs, client=None) -> MarketState:
    ctx = build_agent_contexts(inputs)["market"]
    return analyze_market(ctx, client=client)


def test_regime_is_always_a_valid_enum_token(mock_llm) -> None:
    out = _run(_inputs(), client=mock_llm)  # default FakeLLM body → rule fallback
    assert out.regime in _REGIMES
    MarketState.model_validate(out.model_dump())


def test_index_data_is_passed_through_from_p3_be_1(mock_llm) -> None:
    out = _run(_inputs(index_trend="DOWN", vix=24.5), client=mock_llm)
    assert out.index_trend == "DOWN"
    assert out.vix == 24.5
    assert out.as_of == _NOW


def test_llm_regime_is_used_when_on_enum(mock_llm) -> None:
    mock_llm.response_content = json.dumps({"regime": "risk_off"})
    assert _run(_inputs(index_trend="UP", vix=12.0), client=mock_llm).regime == "RISK_OFF"


def test_off_enum_llm_answer_falls_back_to_the_rule(mock_llm) -> None:
    mock_llm.response_content = json.dumps({"regime": "BANANAS"})
    # vix 30 ≥ high-vol threshold → HIGH_VOL by rule
    assert _run(_inputs(vix=30.0), client=mock_llm).regime == MarketRegime.HIGH_VOL.value


def test_rule_reads_vix_and_trend(mock_llm) -> None:
    mock_llm.response_content = "not json at all"
    assert _run(_inputs(index_trend="UP", vix=11.0), client=mock_llm).regime == "RISK_ON"
    assert _run(_inputs(index_trend="DOWN", vix=15.0), client=mock_llm).regime == "RISK_OFF"
    assert _run(_inputs(index_trend="FLAT", vix=12.0), client=mock_llm).regime == "NEUTRAL"
