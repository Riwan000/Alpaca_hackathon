"""Drawdown, max drawdown and high-water mark over an equity curve (P2-BE-4).

The high-water mark is the running peak of the curve. Per-point drawdown is the
fractional decline from that peak, ``(equity - hwm) / hwm`` (``<= 0``, and
``0`` while the curve is at a new high). Max drawdown is the deepest such
decline, reported as a **non-negative magnitude** — ``0`` for a flat or
monotonically rising curve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "DrawdownPoint",
    "DrawdownResult",
    "high_water_marks",
    "drawdown_series",
    "max_drawdown",
    "compute_drawdown",
]


@dataclass(frozen=True)
class DrawdownPoint:
    """One sample of the equity curve with its running drawdown state."""

    index: int
    equity: float
    high_water_mark: float
    drawdown: float


@dataclass(frozen=True)
class DrawdownResult:
    """Drawdown analysis of a full equity curve.

    ``max_drawdown`` is a non-negative magnitude; ``peak_index`` /
    ``trough_index`` bracket the deepest decline; ``current_drawdown`` is the
    signed drawdown at the final sample.
    """

    points: tuple[DrawdownPoint, ...]
    high_water_mark: float
    current_drawdown: float
    max_drawdown: float
    peak_index: int
    trough_index: int


def _require_non_empty(curve: Sequence[float]) -> None:
    if len(curve) == 0:
        raise ValueError("equity curve is empty")


def _point_drawdown(equity: float, high_water_mark: float) -> float:
    # A percentage drawdown needs a positive peak to divide by.
    if high_water_mark <= 0:
        return 0.0
    return (equity - high_water_mark) / high_water_mark


def high_water_marks(curve: Sequence[float]) -> list[float]:
    """Running peak of ``curve`` at each index."""
    _require_non_empty(curve)
    peak = curve[0]
    marks: list[float] = []
    for value in curve:
        if value > peak:
            peak = value
        marks.append(peak)
    return marks


def drawdown_series(curve: Sequence[float]) -> list[float]:
    """Per-point drawdown fraction relative to the running high-water mark."""
    return [
        _point_drawdown(value, mark)
        for value, mark in zip(curve, high_water_marks(curve))
    ]


def max_drawdown(curve: Sequence[float]) -> float:
    """Deepest peak-to-trough decline as a non-negative fraction."""
    return abs(min(drawdown_series(curve)))


def compute_drawdown(curve: Sequence[float]) -> DrawdownResult:
    """Full drawdown analysis of ``curve``."""
    _require_non_empty(curve)
    points: list[DrawdownPoint] = []
    peak_index = 0
    max_dd = 0.0
    trough_index = 0
    max_dd_peak_index = 0
    for index, equity in enumerate(curve):
        if equity > curve[peak_index]:
            peak_index = index
        mark = curve[peak_index]
        drawdown = _point_drawdown(equity, mark)
        points.append(
            DrawdownPoint(
                index=index,
                equity=equity,
                high_water_mark=mark,
                drawdown=drawdown,
            )
        )
        if -drawdown > max_dd:
            max_dd = -drawdown
            trough_index = index
            max_dd_peak_index = peak_index
    return DrawdownResult(
        points=tuple(points),
        high_water_mark=curve[peak_index],
        current_drawdown=points[-1].drawdown,
        max_drawdown=max_dd,
        peak_index=max_dd_peak_index,
        trough_index=trough_index,
    )
