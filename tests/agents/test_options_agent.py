"""Options Analysis Agent tests — task P3-BE-9 (BRD §13).

Candidates must respect the liquidity threshold and sit inside the configured
expiry window; the list is capped per underlying and ranked by open interest.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.context_builder import AnalysisInputs, build_agent_contexts
from backend.agents.options import OptionsFilterConfig, analyze_options
from backend.models.hedge_context import OptionCandidate

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_TODAY = _NOW.date()
_CFG = OptionsFilterConfig()


def _quote(**over):
    base = {
        "right": "PUT",
        "strike": 100.0,
        "expiration": "2026-10-03",  # dte 30
        "bid": 1.00,
        "ask": 1.10,
        "last": 1.05,
        "volume": 50,
        "open_interest": 500,
        "iv": 0.22,
        "delta": -0.30,
    }
    base.update(over)
    return base


def _inputs(chains: list[dict]) -> AnalysisInputs:
    return AnalysisInputs.model_validate(
        {
            "cycle_id": "cyc-p3-be-9",
            "timestamp": _NOW.isoformat(),
            "objective": {"max_hedge_budget_pct": 0.05, "drawdown_tolerance_pct": 0.1},
            "portfolio_state": {
                "total_value": 100_000.0, "cash": 40_000.0, "equity": 60_000.0,
                "buying_power": 20_000.0,
                "positions": [
                    {"symbol": "AAPL", "qty": 100.0, "avg_price": 50.0, "market_value": 20_000.0}
                ],
            },
            "hedge_underlyings": ["AAPL"],
            "option_chains": chains,
        }
    )


def _run(chains: list[dict], *, config: OptionsFilterConfig | None = None) -> list[OptionCandidate]:
    ctx = build_agent_contexts(_inputs(chains))["options"]
    return analyze_options(ctx, config=config, now=_NOW)


def test_liquidity_and_window_gates() -> None:
    chain = {
        "underlying": "AAPL",
        "spot": 100.0,
        "quotes": [
            _quote(strike=95.0),  # kept
            _quote(strike=90.0, open_interest=10),  # illiquid → dropped
            _quote(strike=97.0, expiration="2027-06-18"),  # dte ~288 → dropped
            _quote(strike=98.0, expiration="2026-09-05"),  # dte 2 → dropped
            _quote(strike=99.0, bid=1.00, ask=2.00),  # rel spread 0.67 → dropped
            _quote(strike=96.0, bid=None),  # one-sided → dropped
        ],
    }
    out = _run([chain])
    assert [c.strike for c in out] == [95.0]
    for cand in out:
        assert cand.open_interest >= _CFG.min_open_interest
        dte = (cand.expiration - _TODAY).days
        assert _CFG.min_days_to_expiry <= dte <= _CFG.max_days_to_expiry


def test_premium_is_the_mid_and_iv_is_carried_through() -> None:
    out = _run([{"underlying": "AAPL", "spot": 100.0, "quotes": [_quote()]}])
    assert out[0].premium == pytest.approx(1.05)
    assert out[0].iv == pytest.approx(0.22)
    assert out[0].liquidity in {"high", "ok"}
    OptionCandidate.model_validate(out[0].model_dump())


def test_capped_per_underlying_and_ranked_by_open_interest() -> None:
    quotes = [_quote(strike=float(s), open_interest=oi)
              for s, oi in zip(range(80, 88), [100, 900, 300, 800, 200, 700, 400, 600])]
    out = _run(
        [{"underlying": "AAPL", "spot": 100.0, "quotes": quotes}],
        config=OptionsFilterConfig(max_candidates_per_underlying=3),
    )
    assert len(out) == 3
    assert [c.open_interest for c in out] == [900, 800, 700]


def test_chain_for_a_non_hedge_underlying_is_skipped() -> None:
    chains = [
        {"underlying": "TSLA", "spot": 200.0, "quotes": [_quote()]},
        {"underlying": "AAPL", "spot": 100.0, "quotes": [_quote(strike=95.0)]},
    ]
    out = _run(chains)
    assert {c.underlying for c in out} == {"AAPL"}


def test_empty_when_no_quote_clears_the_gates() -> None:
    chain = {"underlying": "AAPL", "spot": 100.0, "quotes": [_quote(open_interest=1)]}
    assert _run([chain]) == []
