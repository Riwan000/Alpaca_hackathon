"""Hedge ratio — how much of the book's exposure is currently hedged (P2-BE-8).

``hedge_ratio = |hedge notional| / |exposure notional|`` — ``0`` with no hedge
in place, ``1`` when the hedge fully offsets the exposure, ``> 1`` if
over-hedged. ``drift = target − current`` is the signed gap to a target ratio;
:func:`rebalance_notional` turns that gap into the hedge notional to add
(positive) or unwind (negative).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "HedgeAssessment",
    "hedge_ratio",
    "hedge_drift",
    "rebalance_notional",
    "assess_hedge",
]


def hedge_ratio(hedge_notional: float, exposure_notional: float) -> float:
    """``|hedge| / |exposure|``. A flat book (zero exposure) is ``0.0``.

    Both arguments are taken by magnitude, so a hedge booked with the opposite
    sign to the exposure still counts as coverage.
    """
    exposure = abs(exposure_notional)
    if exposure == 0.0:
        return 0.0
    return abs(hedge_notional) / exposure


def hedge_drift(current_ratio: float, target_ratio: float) -> float:
    """Signed gap ``target − current``: positive means under-hedged."""
    return target_ratio - current_ratio


def rebalance_notional(
    exposure_notional: float, current_ratio: float, target_ratio: float
) -> float:
    """Hedge notional to trade to move ``current_ratio`` → ``target_ratio``.

    ``(target − current) · |exposure|`` — positive means add hedge, negative
    means unwind.
    """
    return hedge_drift(current_ratio, target_ratio) * abs(exposure_notional)


@dataclass(frozen=True)
class HedgeAssessment:
    """Current vs target hedge coverage for a book."""

    current_ratio: float
    target_ratio: float
    drift: float
    rebalance_notional: float

    def within_tolerance(self, tolerance: float) -> bool:
        """True when ``|drift|`` is within ``tolerance`` (an absolute gap)."""
        if tolerance < 0:
            raise ValueError(
                f"tolerance must be non-negative, got {tolerance!r}"
            )
        return abs(self.drift) <= tolerance


def assess_hedge(
    hedge_notional: float, exposure_notional: float, target_ratio: float
) -> HedgeAssessment:
    """Build a :class:`HedgeAssessment` from raw notionals and a target ratio."""
    if target_ratio < 0:
        raise ValueError(
            f"target_ratio must be non-negative, got {target_ratio!r}"
        )
    current = hedge_ratio(hedge_notional, exposure_notional)
    return HedgeAssessment(
        current_ratio=current,
        target_ratio=target_ratio,
        drift=hedge_drift(current, target_ratio),
        rebalance_notional=rebalance_notional(
            exposure_notional, current, target_ratio
        ),
    )
