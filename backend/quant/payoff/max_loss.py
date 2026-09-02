"""Worst-case loss, best-case profit and breakevens for a payoff structure (P2-BE-13).

The combined expiration payoff (:func:`backend.quant.payoff.curve.total_payoff`)
is piecewise linear in the underlying, with a kink at every option strike. Its
extrema therefore sit at a strike, at ``spot = 0``, or out at ``spot -> inf`` —
so evaluating the payoff at each strike and at zero, plus the sign of the two
tail slopes, is enough to pin down:

* ``max_loss`` — the worst P&L as a positive number; ``inf`` when the right tail
  falls away without bound (a naked short call, say).
* ``max_profit`` — the best P&L; ``inf`` when the right tail rises without bound.
* ``breakevens`` — the spots where P&L crosses zero, ascending.

A put spread's ``max_loss`` is its net debit; a collar is bounded on both sides.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from backend.quant.payoff.curve import LegKind, PayoffLeg, total_payoff

__all__ = [
    "StructureRisk",
    "tail_slopes",
    "structure_risk",
    "max_loss",
    "max_profit",
    "breakevens",
]

#: P&L within this of zero counts as a breakeven touch rather than a crossing.
_ZERO_TOL = 1e-9
#: Two breakevens closer than this are treated as one.
_MERGE_TOL = 1e-6


def _sorted_strikes(legs: Sequence[PayoffLeg]) -> list[float]:
    """Ascending unique option strikes (``UNDERLYING`` legs have none)."""
    return sorted({leg.strike for leg in legs if leg.kind is not LegKind.UNDERLYING})


def _slope(legs: Sequence[PayoffLeg], spot: float) -> float:
    """Analytic d(total P&L)/d(spot); call only at a spot that is not on a strike."""
    slope = 0.0
    for leg in legs:
        q_mult = leg.quantity * leg.multiplier
        if leg.kind is LegKind.UNDERLYING:
            slope += q_mult
        elif leg.kind is LegKind.CALL:
            if spot > leg.strike:
                slope += q_mult
        else:  # PUT
            if spot < leg.strike:
                slope -= q_mult
    return slope


def tail_slopes(legs: Iterable[PayoffLeg]) -> tuple[float, float]:
    """``(left, right)`` payoff slope below the lowest strike and above the highest."""
    legs = tuple(legs)
    strikes = _sorted_strikes(legs)
    right_probe = (strikes[-1] + 1.0) if strikes else 1.0
    return _slope(legs, 0.0), _slope(legs, right_probe)


def _segment_breakeven(x0: float, y0: float, x1: float, y1: float) -> float | None:
    """Zero-crossing of the segment ``(x0, y0)``–``(x1, y1)``, or ``None``."""
    if abs(y0) <= _ZERO_TOL:
        return x0
    if y0 * y1 < 0.0:
        return x0 - y0 * (x1 - x0) / (y1 - y0)
    return None


def _breakevens(legs: Sequence[PayoffLeg]) -> tuple[float, ...]:
    strikes = _sorted_strikes(legs)
    xs = [0.0, *strikes]
    ys = [total_payoff(legs, x) for x in xs]

    roots: list[float] = []
    for x0, y0, x1, y1 in zip(xs, ys, xs[1:], ys[1:]):
        root = _segment_breakeven(x0, y0, x1, y1)
        if root is not None:
            roots.append(root)
    if abs(ys[-1]) <= _ZERO_TOL:
        roots.append(xs[-1])

    # Right tail beyond the last kink: solve the single linear piece directly.
    x_ref, y_ref = xs[-1], ys[-1]
    right_slope = _slope(legs, x_ref + 1.0)
    if right_slope != 0.0:
        root = x_ref - y_ref / right_slope
        if root > x_ref + _ZERO_TOL:
            roots.append(root)

    roots.sort()
    merged: list[float] = []
    for root in roots:
        if not merged or abs(root - merged[-1]) > _MERGE_TOL:
            merged.append(root)
    return tuple(merged)


@dataclass(frozen=True)
class StructureRisk:
    """Worst/best P&L and zero-crossings of a combined payoff.

    ``max_loss`` is a positive magnitude (``0.0`` for a structure that cannot
    lose), ``inf`` when unbounded. ``max_profit`` is a signed P&L, ``inf`` when
    unbounded. ``worst_pnl`` / ``best_pnl`` are the same extrema as raw P&L.
    """

    max_loss: float
    max_profit: float
    worst_pnl: float
    best_pnl: float
    breakevens: tuple[float, ...]


def structure_risk(legs: Iterable[PayoffLeg]) -> StructureRisk:
    """Full worst/best/breakeven analysis of a payoff structure."""
    legs = tuple(legs)
    if not legs:
        raise ValueError("need at least one leg")

    _, right_slope = tail_slopes(legs)
    spots = [0.0, *_sorted_strikes(legs)]
    pnls = [total_payoff(legs, spot) for spot in spots]
    worst, best = min(pnls), max(pnls)

    unbounded_loss = right_slope < 0.0
    unbounded_profit = right_slope > 0.0
    return StructureRisk(
        max_loss=math.inf if unbounded_loss else max(0.0, -worst),
        max_profit=math.inf if unbounded_profit else best,
        worst_pnl=-math.inf if unbounded_loss else worst,
        best_pnl=math.inf if unbounded_profit else best,
        breakevens=_breakevens(legs),
    )


def max_loss(legs: Iterable[PayoffLeg]) -> float:
    """Worst-case loss as a positive number; ``inf`` if unbounded."""
    return structure_risk(legs).max_loss


def max_profit(legs: Iterable[PayoffLeg]) -> float:
    """Best-case P&L; ``inf`` if unbounded."""
    return structure_risk(legs).max_profit


def breakevens(legs: Iterable[PayoffLeg]) -> tuple[float, ...]:
    """Ascending spots where the combined P&L crosses zero."""
    return structure_risk(legs).breakevens
