"""Expiration payoff of an option leg or a multi-leg combination (P2-BE-12).

Every structure the hedge agents build — a protective put, a put spread, a
collar — is a handful of legs whose terminal value is piecewise linear in the
underlying price. This module is the one place that knows those payoff shapes:

* :class:`PayoffLeg` — one leg: a call, a put, or the underlying itself.
* :func:`leg_payoff` / :func:`total_payoff` — P&L at a given expiration spot.
* :func:`payoff_curve` — a sampled ``(spot, pnl)`` curve for charting.

P&L is measured against entry cost, so a long option starts the curve down by
its premium and a protective put sits at a flat ``-premium`` floor below the
strike, then rises with slope 1. :mod:`backend.quant.payoff.max_loss` reuses
these shapes for worst-case and breakeven analysis.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "LegKind",
    "PayoffLeg",
    "PayoffPoint",
    "OPTION_MULTIPLIER",
    "to_leg_kind",
    "leg_intrinsic",
    "leg_entry_debit",
    "leg_payoff",
    "total_payoff",
    "payoff_curve",
]

#: Notional multiplier for a standard US listed option contract.
OPTION_MULTIPLIER: float = 100.0


class LegKind(str, Enum):
    """What a payoff leg is: a call, a put, or a holding of the underlying."""

    CALL = "CALL"
    PUT = "PUT"
    UNDERLYING = "UNDERLYING"


def to_leg_kind(kind: LegKind | str) -> LegKind:
    """Coerce a loose value to :class:`LegKind` (any case, wire enum, or member)."""
    if isinstance(kind, LegKind):
        return kind
    raw = kind.value if isinstance(kind, Enum) else kind
    try:
        return LegKind(str(raw).strip().upper())
    except ValueError:
        raise ValueError(
            f"kind must be a call, put or underlying, got {kind!r}"
        ) from None


@dataclass(frozen=True)
class PayoffLeg:
    """One leg of a payoff structure.

    ``quantity`` is **signed** — positive is long, negative is short — and counts
    contracts for an option, units (shares) for an ``UNDERLYING`` leg.
    ``strike`` is the option strike and is ignored for ``UNDERLYING``.
    ``premium`` is the per-unit price transacted at entry: the option premium, or
    the entry share price for an ``UNDERLYING`` leg. ``multiplier`` scales one
    unit to notional — ``100`` for a standard listed option, ``1`` for shares.
    """

    kind: LegKind
    quantity: float
    strike: float = 0.0
    premium: float = 0.0
    multiplier: float = OPTION_MULTIPLIER

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", to_leg_kind(self.kind))
        if self.quantity == 0:
            raise ValueError("quantity must be non-zero")
        if self.premium < 0:
            raise ValueError(f"premium must be non-negative, got {self.premium!r}")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier!r}")
        if self.kind is not LegKind.UNDERLYING and self.strike <= 0:
            raise ValueError(f"strike must be positive, got {self.strike!r}")


def leg_intrinsic(leg: PayoffLeg, spot: float) -> float:
    """Signed terminal (expiration) value of the leg's contract, premium aside."""
    q_mult = leg.quantity * leg.multiplier
    if leg.kind is LegKind.CALL:
        return q_mult * max(spot - leg.strike, 0.0)
    if leg.kind is LegKind.PUT:
        return q_mult * max(leg.strike - spot, 0.0)
    return q_mult * spot  # UNDERLYING


def leg_entry_debit(leg: PayoffLeg) -> float:
    """Signed cash paid at entry: ``quantity * premium * multiplier`` (credit if short)."""
    return leg.quantity * leg.premium * leg.multiplier


def leg_payoff(leg: PayoffLeg, spot: float) -> float:
    """Leg P&L at expiration spot ``spot`` — terminal value minus entry cost."""
    if spot < 0:
        raise ValueError(f"spot must be non-negative, got {spot!r}")
    return leg_intrinsic(leg, spot) - leg_entry_debit(leg)


def total_payoff(legs: Iterable[PayoffLeg], spot: float) -> float:
    """Combined P&L of ``legs`` at expiration spot ``spot``."""
    return sum((leg_payoff(leg, spot) for leg in legs), 0.0)


@dataclass(frozen=True)
class PayoffPoint:
    """One ``(spot, pnl)`` sample of a payoff curve."""

    spot: float
    pnl: float


def payoff_curve(
    legs: Iterable[PayoffLeg],
    low: float,
    high: float,
    steps: int = 50,
) -> tuple[PayoffPoint, ...]:
    """Sample the combined payoff on ``steps + 1`` evenly spaced spots in ``[low, high]``.

    Requires ``0 <= low < high`` and ``steps >= 1``.
    """
    if low < 0:
        raise ValueError(f"low must be non-negative, got {low!r}")
    if high <= low:
        raise ValueError(f"high must exceed low, got low={low!r}, high={high!r}")
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps!r}")
    legs = tuple(legs)
    span = high - low
    points: list[PayoffPoint] = []
    for i in range(steps + 1):
        spot = low + span * i / steps
        points.append(PayoffPoint(spot=spot, pnl=total_payoff(legs, spot)))
    return tuple(points)
