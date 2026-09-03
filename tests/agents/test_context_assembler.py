"""``HedgeContext`` assembler tests — task P3-BE-10 (BRD §14, §31).

Two guarantees:

* full inputs + every agent healthy → a schema-valid ``HedgeContext`` with every
  section populated and ``degraded_sections`` empty;
* any single agent raising → the context is still returned and validates, that
  agent's section is at its safe default and its name is in
  ``degraded_sections`` (the code-level stand-in for the P3-BE-10 "Confirm":
  kill one agent, ``/analyze`` still returns 200 with a ``degraded`` marker —
  the HTTP half rides on P3-BE-12).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.agents import ANALYSIS_AGENTS
from backend.agents.assembler import (
    AGENT_TO_SECTION,
    ANALYSIS_AGENT_FNS,
    assemble_hedge_context,
)
from backend.agents.base import AgentError
from backend.agents.context_builder import AnalysisInputs
from backend.models.hedge_context import HedgeContext, PortfolioState

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
# Options DTE is checked against wall-clock "today"; keep the sample expiry in the
# agent's [7, 90] day window on whatever day the suite runs.
_EXPIRY = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

_POSITIONS = [
    {"symbol": "AAPL", "qty": 100.0, "avg_price": 150.0, "market_value": 22_500.0},
    {"symbol": "NVDA", "qty": 150.0, "avg_price": 100.0, "market_value": 18_000.0},
]


def _inputs() -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-10",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 140_500.0,
                "cash": 100_000.0,
                "equity": 40_500.0,
                "buying_power": 50_000.0,
                "positions": _POSITIONS,
                # deliberately wrong — the Portfolio agent overwrites these; when
                # it is killed the raw snapshot (these values) is what survives.
                "gross_exposure": 1.0,
                "net_exposure": 1.0,
                "concentration_hhi": 0.999,
            },
            "market_data": {
                "index_symbol": "SPY",
                "index_trend": "DOWN",
                "index_price": 498.2,
                "vix": 24.5,
                "sector_trends": {"tech": "DOWN"},
                "macro_notes": ["Fed on hold"],
                "per_symbol": [
                    {"symbol": "AAPL", "last_price": 150.0, "prior_close": 152.0, "realized_vol": 0.28},
                    {"symbol": "NVDA", "last_price": 120.0, "prior_close": 118.0, "realized_vol": 0.35},
                ],
                "as_of": _NOW.isoformat(),
            },
            "news_feed": [
                {
                    "headline": "AAPL guides revenue below consensus",
                    "ts": _NOW.isoformat(),
                    "body": "Apple cut its quarterly outlook.",
                    "symbols": ["AAPL"],
                    "source": "reuters",
                },
                {
                    "headline": "Markets drift ahead of data",
                    "ts": _NOW.isoformat(),
                    "body": "A routine session.",
                    "symbols": [],
                    "source": "wire",
                },
            ],
            "option_chains": [
                {
                    "underlying": "AAPL",
                    "spot": 150.0,
                    "quotes": [
                        {
                            "right": "PUT",
                            "strike": 145.0,
                            "expiration": _EXPIRY,
                            "bid": 3.10,
                            "ask": 3.20,
                            "volume": 900,
                            "open_interest": 4200,
                            "iv": 0.30,
                            "delta": -0.35,
                        }
                    ],
                }
            ],
            "hedge_underlyings": ["AAPL"],
        }
    )


# --------------------------------------------------------------------------- #
# happy path — every section populated, nothing degraded
# --------------------------------------------------------------------------- #


def test_full_inputs_yield_a_complete_hedge_context(mock_llm) -> None:
    ctx = assemble_hedge_context(_inputs(), client=mock_llm)

    assert isinstance(ctx, HedgeContext)
    assert ctx.degraded_sections == []
    assert ctx.cycle_id == "cyc-p3-be-10"
    assert ctx.timestamp == _NOW
    # every agent-populated section is present and non-empty
    assert ctx.market_state is not None and ctx.market_state.regime
    assert [v.symbol for v in ctx.stock_state] == ["AAPL", "NVDA"]
    assert [n.headline for n in ctx.news_context] == ["AAPL guides revenue below consensus"]
    assert ctx.news_context[0].symbols == ["AAPL"]
    assert [c.underlying for c in ctx.option_candidates] == ["AAPL"]
    # portfolio numbers are the agent's recomputation, not the wrong placeholders
    assert ctx.portfolio_state.gross_exposure == pytest.approx(40_500.0)
    assert ctx.portfolio_state.concentration_hhi != 0.999


def test_complete_context_round_trips(mock_llm) -> None:
    ctx = assemble_hedge_context(_inputs(), client=mock_llm)
    assert HedgeContext.model_validate(ctx.model_dump()) == ctx


def test_client_is_threaded_through_to_the_llm_backed_agents(mock_llm) -> None:
    assemble_hedge_context(_inputs(), client=mock_llm)
    # market / stock / news each make one batched call with the injected client
    assert len(mock_llm.calls) >= 3


# --------------------------------------------------------------------------- #
# degraded path — one agent down, the rest of the context intact
# --------------------------------------------------------------------------- #


def _boom(*_a: Any, **_k: Any) -> Any:
    raise AgentError("killed for the test")


@pytest.mark.parametrize("victim", list(ANALYSIS_AGENTS))
def test_killing_one_agent_degrades_only_its_section(mock_llm, victim: str) -> None:
    section = AGENT_TO_SECTION[victim]
    fns = {**ANALYSIS_AGENT_FNS, victim: _boom}

    ctx = assemble_hedge_context(_inputs(), client=mock_llm, agent_fns=fns)

    # still a valid, round-trippable HedgeContext with exactly one degraded marker
    assert isinstance(ctx, HedgeContext)
    assert ctx.degraded_sections == [section]
    HedgeContext.model_validate(ctx.model_dump())

    # the killed section is at its safe default …
    if section == "portfolio_state":
        assert ctx.portfolio_state.gross_exposure == 1.0  # raw snapshot fallback
        assert ctx.portfolio_state.concentration_hhi == 0.999
    elif section == "market_state":
        assert ctx.market_state is None
    else:
        assert getattr(ctx, section) == []

    # … and every other section is still populated
    healthy = {s for a, s in AGENT_TO_SECTION.items() if a != victim}
    if "market_state" in healthy:
        assert ctx.market_state is not None
    if "stock_state" in healthy:
        assert len(ctx.stock_state) == 2
    if "news_context" in healthy:
        assert len(ctx.news_context) == 1
    if "option_candidates" in healthy:
        assert len(ctx.option_candidates) == 1
    if "portfolio_state" in healthy:
        assert ctx.portfolio_state.gross_exposure == pytest.approx(40_500.0)


def test_a_non_agent_error_also_degrades_rather_than_propagates(mock_llm) -> None:
    def _explode(*_a: Any, **_k: Any) -> Any:
        raise ValueError("not an AgentError")

    ctx = assemble_hedge_context(
        _inputs(), client=mock_llm, agent_fns={**ANALYSIS_AGENT_FNS, "stock": _explode}
    )
    assert ctx.degraded_sections == ["stock_state"]
    assert ctx.stock_state == []


def test_two_agents_down_lists_both_sections_in_agent_order(mock_llm) -> None:
    fns = {**ANALYSIS_AGENT_FNS, "market": _boom, "news": _boom}
    ctx = assemble_hedge_context(_inputs(), client=mock_llm, agent_fns=fns)
    # ANALYSIS_AGENTS order is portfolio, stock, market, news, options
    assert ctx.degraded_sections == ["market_state", "news_context"]
    assert ctx.market_state is None
    assert ctx.news_context == []
    assert len(ctx.stock_state) == 2  # untouched


def test_degraded_portfolio_still_satisfies_the_required_section(mock_llm) -> None:
    ctx = assemble_hedge_context(
        _inputs(), client=mock_llm, agent_fns={**ANALYSIS_AGENT_FNS, "portfolio": _boom}
    )
    assert "portfolio_state" in ctx.degraded_sections
    assert isinstance(ctx.portfolio_state, PortfolioState)
    # the required field is filled from the raw pre-enrichment snapshot
    assert ctx.portfolio_state.total_value == 140_500.0
    assert [p.symbol for p in ctx.portfolio_state.positions] == ["AAPL", "NVDA"]


def test_warning_is_logged_for_a_degraded_section(mock_llm, caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="backend.agents.assembler"):
        assemble_hedge_context(
            _inputs(), client=mock_llm, agent_fns={**ANALYSIS_AGENT_FNS, "options": _boom}
        )
    assert any(
        "options" in rec.message and "degraded" in rec.message
        for rec in caplog.records
    )
