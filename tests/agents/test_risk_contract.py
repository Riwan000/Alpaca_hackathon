"""Deterministic risk engine — contract-validity + expiration screens — P5-BE-4.

Two hard gates beside the P5-BE-1/2 limits (BRD §19):

* **contract validity** — a hedge leg that matches no contract the Options
  Analysis Agent surfaced cannot be validated as real and is rejected;
* **expiration window** — a leg already past expiry is rejected; so is one
  expiring inside the minimum time-to-expiry window. Exactly ``min_days`` out
  passes.

"Now" is the context snapshot time, so the screens replay deterministically.
The confirm scenario rejects an already-expired option.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.agents.risk import (
    DEFAULT_MIN_EXPIRY_DAYS,
    ViolationCode,
    check_contract_validity,
    check_expiration_window,
)
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

pytestmark = pytest.mark.unit

_CYCLE = "cyc-p5-be-4"
_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_TODAY = _NOW.date()
_KNOWN_STRIKE = 145.0
_KNOWN_EXPIRY = date(2026, 10, 3)  # 30 days out


def _context() -> HedgeContext:
    return HedgeContext.model_validate(
        {
            "cycle_id": _CYCLE,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": 100_000.0,
                "cash": 50_000.0,
                "equity": 50_000.0,
                "buying_power": 25_000.0,
                "positions": [],
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": [
                {
                    "underlying": "AAPL",
                    "right": "PUT",
                    "strike": _KNOWN_STRIKE,
                    "expiration": _KNOWN_EXPIRY.isoformat(),
                    "premium": 3.15,
                    "bid": 3.1,
                    "ask": 3.2,
                    "open_interest": 4200,
                }
            ],
        }
    )


def _leg(
    *,
    underlying: str = "AAPL",
    right: OptionRight = OptionRight.PUT,
    strike: float = _KNOWN_STRIKE,
    expiration: date = _KNOWN_EXPIRY,
) -> OptionLeg:
    return OptionLeg(
        underlying=underlying,
        right=right,
        side=OrderSide.BUY,
        strike=strike,
        expiration=expiration,
        quantity=1,
    )


def _hypothesis(*, legs: tuple[OptionLeg, ...] = (_leg(),)) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=_CYCLE,
        strategy=StrategyType.PROTECTIVE_PUT,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=315.0,
        hedge_metrics=HedgeMetrics(hedge_ratio=0.5),
        rationale="synthetic hypothesis for the P5-BE-4 screens",
    )


# --------------------------------------------------------------------------- #
# contract validity
# --------------------------------------------------------------------------- #


def test_leg_matching_an_analyzed_contract_passes() -> None:
    outcome = check_contract_validity(_hypothesis(), _context())

    assert outcome.passed is True
    assert outcome.code is None


def test_unknown_strike_fails() -> None:
    outcome = check_contract_validity(_hypothesis(legs=(_leg(strike=133.0),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.UNKNOWN_CONTRACT
    assert "133" in outcome.detail


def test_unknown_underlying_fails() -> None:
    outcome = check_contract_validity(_hypothesis(legs=(_leg(underlying="MSFT"),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.UNKNOWN_CONTRACT


def test_wrong_expiration_fails() -> None:
    outcome = check_contract_validity(
        _hypothesis(legs=(_leg(expiration=date(2026, 11, 21)),)), _context()
    )

    assert outcome.passed is False
    assert outcome.code is ViolationCode.UNKNOWN_CONTRACT


def test_no_legs_passes_contract_validity() -> None:
    assert check_contract_validity(_hypothesis(legs=()), _context()).passed is True


def test_contract_validity_outcome_maps_to_the_options_category() -> None:
    check = check_contract_validity(_hypothesis(), _context()).to_risk_check()
    assert check.category == "OPTIONS"
    assert check.name == "contract_validity"


# --------------------------------------------------------------------------- #
# expiration window
# --------------------------------------------------------------------------- #


def test_default_min_expiry_window_is_seven_days() -> None:
    assert DEFAULT_MIN_EXPIRY_DAYS == 7


def test_leg_well_beyond_the_window_passes() -> None:
    outcome = check_expiration_window(_hypothesis(), _context())  # 30 days out

    assert outcome.passed is True
    assert outcome.code is None


def test_already_expired_leg_fails_with_the_expired_code() -> None:
    gone = _leg(expiration=date(2026, 8, 29))  # 5 days before _TODAY
    outcome = check_expiration_window(_hypothesis(legs=(gone,)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.CONTRACT_EXPIRED
    assert outcome.observed == pytest.approx(-5.0)


def test_leg_expiring_today_is_inside_the_window() -> None:
    outcome = check_expiration_window(_hypothesis(legs=(_leg(expiration=_TODAY),)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.EXPIRY_WINDOW_VIOLATION
    assert outcome.observed == pytest.approx(0.0)


def test_leg_inside_the_window_fails_with_the_window_code() -> None:
    soon = _leg(expiration=date(2026, 9, 6))  # 3 days out
    outcome = check_expiration_window(_hypothesis(legs=(soon,)), _context())

    assert outcome.passed is False
    assert outcome.code is ViolationCode.EXPIRY_WINDOW_VIOLATION
    assert outcome.observed == pytest.approx(3.0)
    assert outcome.limit == pytest.approx(7.0)


def test_leg_exactly_at_the_window_edge_passes() -> None:
    edge = _leg(expiration=date(2026, 9, 10))  # exactly 7 days out
    outcome = check_expiration_window(_hypothesis(legs=(edge,)), _context())

    assert outcome.passed is True
    assert outcome.code is None


def test_min_days_override_is_honoured() -> None:
    leg = _leg(expiration=date(2026, 9, 20))  # 17 days out
    outcome = check_expiration_window(_hypothesis(legs=(leg,)), _context(), min_days=30)

    assert outcome.passed is False
    assert outcome.code is ViolationCode.EXPIRY_WINDOW_VIOLATION
    assert outcome.limit == pytest.approx(30.0)


def test_no_legs_passes_expiration_window() -> None:
    assert check_expiration_window(_hypothesis(legs=()), _context()).passed is True


def test_expiration_window_outcome_maps_to_the_options_category() -> None:
    check = check_expiration_window(_hypothesis(), _context()).to_risk_check()
    assert check.category == "OPTIONS"
    assert check.name == "expiration_window"


# --------------------------------------------------------------------------- #
# Confirm — an already-expired option is rejected
# --------------------------------------------------------------------------- #


def test_confirm_already_expired_option_is_rejected() -> None:
    ctx = _context()
    expired = _hypothesis(legs=(_leg(expiration=date(2026, 8, 1)),))

    outcome = check_expiration_window(expired, ctx)

    assert outcome.violated is True
    assert outcome.code is ViolationCode.CONTRACT_EXPIRED
    assert "expired" in outcome.detail.lower()
    assert outcome.observed is not None and outcome.observed < 0
