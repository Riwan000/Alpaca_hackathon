"""Shared quant plumbing for the Phase-4 strategy agents (P4-BE-2..5).

The four hedge-family agents each turn a
:class:`~backend.models.hedge_context.HedgeContext` into one
:class:`~backend.models.strategy.StrategyHypothesis`. The *numbers* on that
hypothesis — cost, payoff floor, Greeks — come from :mod:`backend.quant`, never
from an LLM. This module is the handful of helpers they share to get there:

* :func:`primary_holding` — the long equity position a single-name hedge covers;
* :func:`hedge_budget_cash` — the objective's budget as an absolute cash figure;
* :func:`puts_for` / :func:`calls_for` / :func:`nearest_strike` — chain slicing;
* :func:`years_to_expiry` — the calendar-day year fraction Black-Scholes wants;
* :func:`contracts_for_shares` — whole option contracts that cover a holding;
* :func:`leg_greeks` / :func:`combine_greeks` — per-leg BSM Greeks, signed and
  scaled to contracts, then netted across a structure;
* :func:`underlying_leg` / :func:`payoff_points` — the stock leg and a sampled
  portfolio payoff curve as wire :class:`~backend.models.strategy.PayoffPoint`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from backend.models.enums import AssetClass, OptionRight, OrderSide
from backend.models.hedge_context import HedgeContext, OptionCandidate
from backend.models.strategy import PayoffPoint
from backend.quant.greeks import black_scholes
from backend.quant.helpers import CALENDAR_DAYS_PER_YEAR
from backend.quant.payoff import OPTION_MULTIPLIER, PayoffLeg, payoff_curve

__all__ = [
    "RISK_FREE_RATE",
    "DEFAULT_VOLATILITY",
    "OPTION_MULTIPLIER",
    "Holding",
    "primary_holding",
    "hedge_budget_cash",
    "years_to_expiry",
    "puts_for",
    "calls_for",
    "nearest_strike",
    "contracts_for_shares",
    "portfolio_fraction",
    "resolve_volatility",
    "leg_greeks",
    "combine_greeks",
    "underlying_leg",
    "payoff_points",
]

#: Flat risk-free rate for the BSM Greeks the strategy agents report. The hedge
#: decision is not rate-sensitive at these tenors, and a single pinned value
#: keeps every agent's Greeks reproducible for the hand-checks (BRD §16).
RISK_FREE_RATE: float = 0.04

#: Volatility fallback when a candidate carries no IV and the book has no
#: realised-vol estimate.
DEFAULT_VOLATILITY: float = 0.25

#: Payoff curves are sampled across this fractional band around spot.
_CURVE_LOW_FRAC: float = 0.5
_CURVE_HIGH_FRAC: float = 1.5
_CURVE_STEPS: int = 40


@dataclass(frozen=True)
class Holding:
    """The single long equity position a one-name hedge is built around."""

    symbol: str
    shares: float
    market_value: float

    @property
    def spot(self) -> float:
        """Implied current share price — ``market_value / shares``."""
        return self.market_value / self.shares


def primary_holding(context: HedgeContext) -> Holding | None:
    """The largest long equity position in ``context`` — ``None`` if there is none."""
    equities = [
        p
        for p in context.portfolio_state.positions
        if p.asset_class is AssetClass.EQUITY
        and p.side is OrderSide.BUY
        and p.qty > 0
        and p.market_value > 0
    ]
    if not equities:
        return None
    top = max(equities, key=lambda p: p.market_value)
    return Holding(symbol=top.symbol, shares=top.qty, market_value=top.market_value)


def hedge_budget_cash(context: HedgeContext) -> float:
    """The objective's ``max_hedge_budget_pct`` as absolute account currency."""
    return (
        context.objective.max_hedge_budget_pct
        * context.portfolio_state.total_value
    )


def years_to_expiry(context: HedgeContext, expiration: date) -> float:
    """Year fraction from ``context.timestamp`` to ``expiration``.

    Floored at one calendar day so an expiry dated today still prices.
    """
    days = (expiration - context.timestamp.date()).days
    return max(days, 1) / CALENDAR_DAYS_PER_YEAR


def _candidates_for(
    context: HedgeContext, symbol: str, right: OptionRight
) -> list[OptionCandidate]:
    key = symbol.strip().upper()
    return [
        c
        for c in context.option_candidates
        if c.underlying.strip().upper() == key and c.right is right
    ]


def puts_for(context: HedgeContext, symbol: str) -> list[OptionCandidate]:
    """Put candidates on ``symbol`` from the assembled context."""
    return _candidates_for(context, symbol, OptionRight.PUT)


def calls_for(context: HedgeContext, symbol: str) -> list[OptionCandidate]:
    """Call candidates on ``symbol`` from the assembled context."""
    return _candidates_for(context, symbol, OptionRight.CALL)


def nearest_strike(
    candidates: Iterable[OptionCandidate], target: float
) -> OptionCandidate:
    """The candidate whose strike is closest to ``target``.

    Ties break toward the nearer expiry, then the lower strike, so the choice is
    stable for a given context.
    """
    return min(
        candidates,
        key=lambda c: (abs(c.strike - target), c.expiration, c.strike),
    )


def contracts_for_shares(shares: float) -> int:
    """Whole option contracts that cover ``shares`` (one contract = 100 shares)."""
    return math.floor(shares / OPTION_MULTIPLIER)


def portfolio_fraction(cash: float, total_value: float) -> float:
    """``cash / total_value`` as a fraction of the book — ``0.0`` for an empty book.

    Keeps the cost-of-portfolio metric defined (and non-negative) even on a
    degenerate ``total_value <= 0`` context, so a strategy agent reports a
    NOT_VIABLE / no-cost hypothesis rather than raising ``ZeroDivisionError``.
    """
    if total_value <= 0.0:
        return 0.0
    return cash / total_value


def resolve_volatility(
    candidate: OptionCandidate, context: HedgeContext
) -> float:
    """The vol to price a leg with: the candidate IV, else book vol, else default."""
    return (
        candidate.iv
        or context.portfolio_state.volatility
        or DEFAULT_VOLATILITY
    )


def _sign(side: OrderSide) -> int:
    return 1 if side is OrderSide.BUY else -1


def leg_greeks(
    *,
    spot: float,
    strike: float,
    t: float,
    vol: float,
    right: OptionRight,
    contracts: int,
    side: OrderSide,
) -> dict[str, float]:
    """Signed, contract-scaled BSM Greeks for one option leg.

    ``delta / gamma / theta / vega`` come from :func:`backend.quant.greeks.black_scholes`
    and are multiplied by ``sign(side) * contracts * 100`` so a short leg and the
    contract multiplier are already folded in.
    """
    kind = "CALL" if right is OptionRight.CALL else "PUT"
    greeks = black_scholes(spot, strike, t, vol, RISK_FREE_RATE, kind)
    scale = _sign(side) * contracts * OPTION_MULTIPLIER
    return {
        "net_delta": greeks.delta * scale,
        "net_gamma": greeks.gamma * scale,
        "net_theta": greeks.theta * scale,
        "net_vega": greeks.vega * scale,
    }


def combine_greeks(*legs: dict[str, float]) -> dict[str, float]:
    """Sum per-leg Greek dicts key-by-key into one net-Greeks dict."""
    keys = ("net_delta", "net_gamma", "net_theta", "net_vega")
    return {k: sum(leg.get(k, 0.0) for leg in legs) for k in keys}


def underlying_leg(holding: Holding, contracts: int) -> PayoffLeg:
    """A stock leg covering ``contracts * 100`` shares, entered at the current spot."""
    return PayoffLeg(
        kind="UNDERLYING",
        quantity=contracts * OPTION_MULTIPLIER,
        premium=holding.spot,
        multiplier=1.0,
    )


def payoff_points(legs: Iterable[PayoffLeg], spot: float) -> list[PayoffPoint]:
    """Sample the combined payoff around ``spot`` as wire :class:`PayoffPoint` rows."""
    curve = payoff_curve(
        legs,
        spot * _CURVE_LOW_FRAC,
        spot * _CURVE_HIGH_FRAC,
        _CURVE_STEPS,
    )
    return [PayoffPoint(price=point.spot, pnl=point.pnl) for point in curve]
