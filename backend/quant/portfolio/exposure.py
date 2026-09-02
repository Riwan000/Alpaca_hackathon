"""Portfolio exposure — per-position, gross and net (P2-BE-2).

Per-position exposure is the signed notional ``quantity · price · multiplier``.
Gross exposure sums the absolute values; net exposure sums the signed values.
The two are equal for a long-only book and diverge once a short is present.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.quant.portfolio.position import Position, signed_notional

__all__ = [
    "PositionExposure",
    "ExposureBreakdown",
    "position_exposure",
    "compute_exposure",
    "gross_exposure",
    "net_exposure",
]


@dataclass(frozen=True)
class PositionExposure:
    """Signed dollar exposure of a single position."""

    symbol: str
    exposure: float


@dataclass(frozen=True)
class ExposureBreakdown:
    """Aggregated exposure of a book.

    ``long_exposure`` is ``>= 0``, ``short_exposure`` is ``<= 0``,
    ``gross_exposure`` is ``Σ |exposure|``, ``net_exposure`` is ``Σ exposure``.
    """

    per_position: tuple[PositionExposure, ...]
    long_exposure: float
    short_exposure: float
    gross_exposure: float
    net_exposure: float


def position_exposure(position: Position) -> float:
    """Signed dollar exposure: ``quantity · price · multiplier``."""
    return signed_notional(position)


def compute_exposure(positions: Iterable[Position]) -> ExposureBreakdown:
    """Aggregate ``positions`` into an :class:`ExposureBreakdown`."""
    per_position: list[PositionExposure] = []
    long_exposure = 0.0
    short_exposure = 0.0
    gross = 0.0
    for position in positions:
        exposure = signed_notional(position)
        per_position.append(
            PositionExposure(symbol=position.symbol, exposure=exposure)
        )
        gross += abs(exposure)
        if exposure >= 0:
            long_exposure += exposure
        else:
            short_exposure += exposure
    return ExposureBreakdown(
        per_position=tuple(per_position),
        long_exposure=long_exposure,
        short_exposure=short_exposure,
        gross_exposure=gross,
        net_exposure=long_exposure + short_exposure,
    )


def gross_exposure(positions: Iterable[Position]) -> float:
    """Sum of absolute per-position exposures (``>= 0``)."""
    return compute_exposure(positions).gross_exposure


def net_exposure(positions: Iterable[Position]) -> float:
    """Sum of signed per-position exposures (long minus short)."""
    return compute_exposure(positions).net_exposure
