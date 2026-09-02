"""Unit tests for max loss / max profit / breakevens — P2-BE-13.

Put spread: max loss = net debit. Collar: bounded on both sides. Naked short
call: loss unbounded. Breakevens land where the combined P&L crosses zero.
All legs use multiplier 1 so the arithmetic is transparent.
"""

from __future__ import annotations

import math

import pytest

from backend.quant.payoff.curve import LegKind, PayoffLeg
from backend.quant.payoff.max_loss import (
    breakevens,
    max_loss,
    max_profit,
    structure_risk,
    tail_slopes,
)

pytestmark = pytest.mark.unit


def _leg(
    kind: LegKind, quantity: float, strike: float = 0.0, premium: float = 0.0
) -> PayoffLeg:
    return PayoffLeg(
        kind=kind, quantity=quantity, strike=strike, premium=premium, multiplier=1.0
    )


# Bear put debit spread: long 100-strike put @ 6, short 90-strike put @ 2.
# net debit = 4; width = 10; max profit = width - debit = 6; breakeven = 100 - 4 = 96.
PUT_SPREAD = (
    _leg(LegKind.PUT, 1, strike=100.0, premium=6.0),
    _leg(LegKind.PUT, -1, strike=90.0, premium=2.0),
)

# Collar on a share held at 100: long 95-strike put @ 3, short 110-strike call @ 3.
# floor = -5, cap = +10, breakeven = 100.
COLLAR = (
    _leg(LegKind.UNDERLYING, 1, premium=100.0),
    _leg(LegKind.PUT, 1, strike=95.0, premium=3.0),
    _leg(LegKind.CALL, -1, strike=110.0, premium=3.0),
)


def test_put_spread_max_loss_equals_the_net_debit() -> None:
    risk = structure_risk(PUT_SPREAD)

    assert risk.max_loss == pytest.approx(4.0)
    assert risk.max_profit == pytest.approx(6.0)
    assert risk.worst_pnl == pytest.approx(-4.0)
    assert math.isfinite(risk.max_loss)


def test_put_spread_breakeven_is_long_strike_minus_debit() -> None:
    assert breakevens(PUT_SPREAD) == pytest.approx((96.0,))


def test_collar_is_bounded_on_both_sides() -> None:
    risk = structure_risk(COLLAR)

    assert math.isfinite(risk.max_loss)
    assert math.isfinite(risk.max_profit)
    assert risk.max_loss == pytest.approx(5.0)
    assert risk.max_profit == pytest.approx(10.0)


def test_collar_breakeven_is_the_entry_spot() -> None:
    assert breakevens(COLLAR) == pytest.approx((100.0,))


def test_naked_short_call_has_unbounded_loss() -> None:
    short_call = (_leg(LegKind.CALL, -1, strike=100.0, premium=5.0),)
    risk = structure_risk(short_call)

    assert risk.max_loss == math.inf
    assert risk.worst_pnl == -math.inf
    assert risk.max_profit == pytest.approx(5.0)  # keeps the premium
    assert breakevens(short_call) == pytest.approx((105.0,))  # strike + premium


def test_long_call_has_unbounded_profit_and_capped_loss() -> None:
    long_call = (_leg(LegKind.CALL, 1, strike=100.0, premium=5.0),)
    risk = structure_risk(long_call)

    assert risk.max_profit == math.inf
    assert risk.best_pnl == math.inf
    assert risk.max_loss == pytest.approx(5.0)  # the premium
    assert breakevens(long_call) == pytest.approx((105.0,))


def test_protective_put_loss_is_capped_at_the_premium() -> None:
    protective_put = (
        _leg(LegKind.UNDERLYING, 1, premium=100.0),
        _leg(LegKind.PUT, 1, strike=100.0, premium=5.0),
    )

    assert max_loss(protective_put) == pytest.approx(5.0)
    assert max_profit(protective_put) == math.inf
    assert breakevens(protective_put) == pytest.approx((105.0,))


def test_tail_slopes_report_left_and_right_gradients() -> None:
    # collar: left tail flat (put offsets the share), right tail flat (call offsets it).
    assert tail_slopes(COLLAR) == pytest.approx((0.0, 0.0))
    # long call: flat left, slope +1 right.
    assert tail_slopes(
        (_leg(LegKind.CALL, 1, strike=100.0, premium=5.0),)
    ) == pytest.approx((0.0, 1.0))


def test_empty_structure_is_rejected() -> None:
    with pytest.raises(ValueError):
        structure_risk(())
