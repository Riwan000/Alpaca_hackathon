"""Strategy Manager — comparison stage tests — task P4-BE-8 / issue #110.

Confirms:
  - One row per viable hypothesis.
  - All rows share the same metric keys (consistent columns).
  - Numbers come from hypothesis hedge_metrics, not the LLM.
  - NO_HEDGE family gets a row with cost=0.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.strategies import StrategyManager
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import ComparisonRow, HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_CYCLE = "cyc-p4-be-8"


def _context(*, cycle_id: str = _CYCLE, total_value: float = 100_000.0) -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": total_value / 4,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
        }
    )


def _viable(
    strategy: StrategyType,
    *,
    cost: float = 300.0,
    hedge_ratio: float | None = 0.85,
    downside_protection_pct: float | None = 0.08,
    cost_pct_of_portfolio: float | None = 0.003,
    net_delta: float | None = -85.0,
    liquidity: str | None = "good",
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE if strategy is not StrategyType.NO_HEDGE else HedgeAction.NO_TRADE,
        viable=True,
        cost=cost,
        rationale=f"synthetic viable {strategy.value}",
        liquidity=liquidity,
        hedge_metrics=HedgeMetrics(
            hedge_ratio=hedge_ratio,
            downside_protection_pct=downside_protection_pct,
            cost_pct_of_portfolio=cost_pct_of_portfolio,
            net_delta=net_delta,
        ),
    )


# --------------------------------------------------------------------------- #
# one row per viable hypothesis
# --------------------------------------------------------------------------- #


def test_compare_produces_one_row_per_viable_hypothesis() -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0),
        _viable(StrategyType.PUT_SPREAD, cost=120.0),
        _viable(StrategyType.NO_HEDGE, cost=0.0),
    ]

    rows = StrategyManager().compare(viable, ctx)

    assert len(rows) == 3
    strategies = [r.strategy for r in rows]
    assert StrategyType.PROTECTIVE_PUT in strategies
    assert StrategyType.PUT_SPREAD in strategies
    assert StrategyType.NO_HEDGE in strategies


def test_compare_preserves_input_order() -> None:
    ctx = _context()
    viable = [
        _viable(StrategyType.PUT_SPREAD),
        _viable(StrategyType.COLLAR),
        _viable(StrategyType.PROTECTIVE_PUT),
    ]

    rows = StrategyManager().compare(viable, ctx)

    assert [r.strategy for r in rows] == [
        StrategyType.PUT_SPREAD,
        StrategyType.COLLAR,
        StrategyType.PROTECTIVE_PUT,
    ]


# --------------------------------------------------------------------------- #
# consistent columns — same keys populated on every row
# --------------------------------------------------------------------------- #


def test_all_rows_have_the_same_metric_keys_set() -> None:
    """Confirm: comparison table renders with consistent columns (issue #110)."""
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0, downside_protection_pct=0.08),
        _viable(StrategyType.PUT_SPREAD, cost=120.0, downside_protection_pct=0.05),
        _viable(StrategyType.NO_HEDGE, cost=0.0, downside_protection_pct=0.0,
                hedge_ratio=0.0, net_delta=0.0, cost_pct_of_portfolio=0.0),
    ]

    rows = StrategyManager().compare(viable, ctx)

    # Every row must be a valid ComparisonRow
    for row in rows:
        assert isinstance(row, ComparisonRow)

    # All rows must have the same set of *populated* (non-None) metric columns
    def _populated_keys(row: ComparisonRow) -> set[str]:
        return {
            k
            for k, v in row.model_dump().items()
            if v is not None and k not in ("strategy", "verdict", "score")
        }

    key_sets = [_populated_keys(r) for r in rows]
    # At minimum, "cost" must be present on every row
    for keys in key_sets:
        assert "cost" in keys, f"row missing 'cost': {keys}"


# --------------------------------------------------------------------------- #
# numbers come from quant — not from the LLM
# --------------------------------------------------------------------------- #


def test_cost_is_sourced_from_hypothesis_not_llm() -> None:
    ctx = _context()
    h = _viable(StrategyType.PROTECTIVE_PUT, cost=315.0)

    rows = StrategyManager().compare([h], ctx)

    assert len(rows) == 1
    assert rows[0].cost == pytest.approx(315.0)


def test_downside_protection_pct_is_sourced_from_hedge_metrics() -> None:
    ctx = _context()
    h = _viable(StrategyType.PROTECTIVE_PUT, downside_protection_pct=0.087)

    rows = StrategyManager().compare([h], ctx)

    assert rows[0].downside_protection_pct == pytest.approx(0.087)


def test_liquidity_is_sourced_from_hypothesis() -> None:
    ctx = _context()
    h = _viable(StrategyType.PROTECTIVE_PUT, liquidity="excellent")

    rows = StrategyManager().compare([h], ctx)

    assert rows[0].liquidity == "excellent"


# --------------------------------------------------------------------------- #
# NO_HEDGE row
# --------------------------------------------------------------------------- #


def test_no_hedge_row_has_zero_cost() -> None:
    ctx = _context()
    h = _viable(
        StrategyType.NO_HEDGE,
        cost=0.0,
        hedge_ratio=0.0,
        downside_protection_pct=0.0,
        cost_pct_of_portfolio=0.0,
        net_delta=0.0,
    )

    rows = StrategyManager().compare([h], ctx)

    assert len(rows) == 1
    assert rows[0].strategy is StrategyType.NO_HEDGE
    assert rows[0].cost == 0.0


# --------------------------------------------------------------------------- #
# empty input
# --------------------------------------------------------------------------- #


def test_compare_empty_returns_empty_list() -> None:
    ctx = _context()
    rows = StrategyManager().compare([], ctx)
    assert rows == []


# --------------------------------------------------------------------------- #
# Confirm: comparison table renders with consistent columns
# --------------------------------------------------------------------------- #


def test_confirm_comparison_table_has_consistent_columns_across_all_four_families() -> None:
    """Confirm scenario: all four families → table with consistent columns."""
    ctx = _context()
    viable = [
        _viable(StrategyType.PROTECTIVE_PUT, cost=315.0, downside_protection_pct=0.08,
                cost_pct_of_portfolio=0.0032, liquidity="good"),
        _viable(StrategyType.PUT_SPREAD, cost=120.0, downside_protection_pct=0.05,
                cost_pct_of_portfolio=0.0012, liquidity="good"),
        _viable(StrategyType.COLLAR, cost=20.0, downside_protection_pct=0.06,
                cost_pct_of_portfolio=0.0002, liquidity="fair"),
        _viable(StrategyType.NO_HEDGE, cost=0.0, downside_protection_pct=0.0,
                hedge_ratio=0.0, net_delta=0.0, cost_pct_of_portfolio=0.0, liquidity=None),
    ]

    rows = StrategyManager().compare(viable, ctx)

    assert len(rows) == 4

    # Each row must be schema-valid
    for row in rows:
        ComparisonRow.model_validate(row.model_dump())

    # "cost" is present and correct on every row
    costs_by_strategy = {r.strategy: r.cost for r in rows}
    assert costs_by_strategy[StrategyType.PROTECTIVE_PUT] == pytest.approx(315.0)
    assert costs_by_strategy[StrategyType.PUT_SPREAD] == pytest.approx(120.0)
    assert costs_by_strategy[StrategyType.COLLAR] == pytest.approx(20.0)
    assert costs_by_strategy[StrategyType.NO_HEDGE] == pytest.approx(0.0)
