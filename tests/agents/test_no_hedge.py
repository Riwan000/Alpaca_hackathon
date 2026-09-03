"""No-Hedge agent tests — task P4-BE-5 (BRD §15–16).

Always VIABLE — an unhedged book is a real alternative the Strategy Manager must
weigh — and the rationale always states the current drawdown against the
objective's tolerance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.agents.strategies import NoHedgeAgent
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "analyze"
    / "hedge_context_golden.json"
)


def _context(*, drawdown: float | None, tolerance: float = 0.10) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": "cyc-p4-be-5",
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "drawdown": drawdown,
                "gross_exposure": 50_000.0,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": tolerance,
            },
        }
    )


def test_seed_context_is_viable_and_cites_drawdown_within_tolerance() -> None:
    ctx = HedgeContext.model_validate(json.loads(_GOLDEN.read_text("utf-8")))

    hyp = NoHedgeAgent().propose(ctx)

    assert hyp.viable is True
    assert hyp.strategy is StrategyType.NO_HEDGE
    assert hyp.action is HedgeAction.NO_TRADE
    assert hyp.cost == 0.0
    # golden drawdown is -0.0460..., tolerance 0.10
    assert "drawdown" in hyp.rationale.lower()
    assert "4.6%" in hyp.rationale
    assert "10.0%" in hyp.rationale
    assert "within" in hyp.rationale
    assert StrategyHypothesis.model_validate(hyp.model_dump()) == hyp


def test_still_viable_when_drawdown_is_beyond_tolerance() -> None:
    hyp = NoHedgeAgent().propose(_context(drawdown=-0.15))

    assert hyp.viable is True
    assert hyp.action is HedgeAction.NO_TRADE
    assert "15.0%" in hyp.rationale
    assert "beyond" in hyp.rationale
    assert "drawdown" in hyp.rationale.lower()


def test_viable_even_with_no_drawdown_recorded() -> None:
    hyp = NoHedgeAgent().propose(_context(drawdown=None))

    assert hyp.viable is True
    assert "0.0%" in hyp.rationale
    assert "within" in hyp.rationale
    assert hyp.hedge_metrics.hedge_ratio == 0.0
    assert hyp.hedge_metrics.downside_protection_pct == 0.0


def test_rejection_reason_is_never_set() -> None:
    hyp = NoHedgeAgent().propose(_context(drawdown=-0.02))

    assert hyp.rejection_reason is None
    assert hyp.rejection_conditions  # non-empty — when NO_HEDGE stops being fine
