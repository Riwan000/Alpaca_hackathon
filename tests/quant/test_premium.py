"""Unit tests for premium / hedge cost as a fraction of portfolio value — P2-BE-11.

cost fraction = premium * contracts * multiplier / portfolio value; a sold leg is
a credit and lowers the net; a non-positive portfolio value is rejected.
"""

from __future__ import annotations

import pytest

from backend.quant.payoff.premium import (
    PremiumCost,
    cost_fraction,
    hedge_cost,
    net_premium_cash,
    premium_cash,
    premium_cost,
)

pytestmark = pytest.mark.unit

PREMIUM = 3.20
CONTRACTS = 5
MULTIPLIER = 100.0
PORTFOLIO_VALUE = 250_000.0
#: 3.20 * 5 * 100 = 1600 cash; 1600 / 250000 = 0.0064.
EXPECTED_CASH = 1_600.0
EXPECTED_FRACTION = 0.0064


def test_premium_cash_is_premium_times_contracts_times_multiplier() -> None:
    assert premium_cash(PREMIUM, CONTRACTS, MULTIPLIER) == pytest.approx(EXPECTED_CASH)


def test_premium_cash_defaults_to_the_listed_option_multiplier() -> None:
    assert premium_cash(PREMIUM, CONTRACTS) == pytest.approx(EXPECTED_CASH)


def test_cost_fraction_is_cash_over_portfolio_value() -> None:
    assert cost_fraction(EXPECTED_CASH, PORTFOLIO_VALUE) == pytest.approx(
        EXPECTED_FRACTION
    )


def test_premium_cost_reports_cash_and_fraction_and_percent() -> None:
    cost = premium_cost(PREMIUM, CONTRACTS, PORTFOLIO_VALUE, MULTIPLIER)

    assert isinstance(cost, PremiumCost)
    assert cost.cash == pytest.approx(EXPECTED_CASH)
    assert cost.fraction_of_portfolio == pytest.approx(EXPECTED_FRACTION)
    assert cost.pct_of_portfolio == pytest.approx(0.64)


def test_zero_premium_is_zero_cost() -> None:
    cost = premium_cost(0.0, CONTRACTS, PORTFOLIO_VALUE)

    assert cost.cash == 0.0
    assert cost.fraction_of_portfolio == 0.0


def test_net_premium_cash_debit_spread_is_positive() -> None:
    # long put @ 6.00, short put @ 2.00, one contract each, standard multiplier.
    net = net_premium_cash([(6.0, 1, 100.0), (2.0, -1, 100.0)])

    assert net == pytest.approx(400.0)  # (6 - 2) * 1 * 100


def test_net_premium_cash_credit_structure_is_negative() -> None:
    # collar financed by the short call: long put @ 3.00, short call @ 4.00.
    net = net_premium_cash([(3.0, 1, 100.0), (4.0, -1, 100.0)])

    assert net == pytest.approx(-100.0)


def test_hedge_cost_fraction_is_signed_by_the_net() -> None:
    cost = hedge_cost([(3.0, 1, 100.0), (4.0, -1, 100.0)], PORTFOLIO_VALUE)

    assert cost.cash == pytest.approx(-100.0)
    assert cost.fraction_of_portfolio == pytest.approx(-0.0004)


@pytest.mark.parametrize("portfolio_value", [0.0, -1.0, -250_000.0])
def test_non_positive_portfolio_value_is_rejected(portfolio_value: float) -> None:
    with pytest.raises(ValueError):
        cost_fraction(EXPECTED_CASH, portfolio_value)
    with pytest.raises(ValueError):
        premium_cost(PREMIUM, CONTRACTS, portfolio_value)


@pytest.mark.parametrize(
    ("premium", "contracts", "multiplier"),
    [
        (-0.01, CONTRACTS, MULTIPLIER),
        (PREMIUM, -1, MULTIPLIER),
        (PREMIUM, CONTRACTS, 0.0),
    ],
)
def test_bad_leg_inputs_are_rejected(
    premium: float, contracts: float, multiplier: float
) -> None:
    with pytest.raises(ValueError):
        premium_cash(premium, contracts, multiplier)


def test_net_premium_cash_rejects_a_negative_premium() -> None:
    with pytest.raises(ValueError):
        net_premium_cash([(-1.0, 1, 100.0)])
