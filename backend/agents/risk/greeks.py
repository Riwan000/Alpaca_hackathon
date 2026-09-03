"""Greeks-bounds + multi-leg consistency screens — task **P5-BE-5** (BRD §19).

* :func:`check_net_delta_bounds` — the proposal's net delta must sit inside the
  band a *hedge overlay* is allowed: it may not add net-long directional
  exposure beyond a slop tolerance, and it may not over-hedge past the shares
  it covers. Net delta is share-equivalent (``Σ δ · sign(side) · contracts ·
  100``), and a hypothesis whose ``hedge_metrics.net_delta`` is unset is not
  evaluated.
* :func:`check_multileg_consistency` — a multi-leg structure must be internally
  coherent: a put spread needs two puts with the long strike above the short
  strike, a collar needs both a long put and a short call, and no structure may
  span underlyings.

Both functions are pure. No LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.engine import CheckOutcome
from backend.models.common import OptionLeg
from backend.models.enums import AssetClass, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import StrategyHypothesis

__all__ = [
    "DELTA_TOLERANCE_SHARES",
    "NetDeltaBounds",
    "check_multileg_consistency",
    "check_net_delta_bounds",
]

#: Share-equivalent net-delta slop a hedge is allowed on either side of its
#: nominal band — roughly a quarter of one option contract.
DELTA_TOLERANCE_SHARES: float = 25.0

#: Fraction of the covered share count added to :data:`DELTA_TOLERANCE_SHARES`
#: as the band's margin, so the tolerance scales with position size.
_MARGIN_FRACTION: float = 0.15

_OPTIONS = "OPTIONS"
_NET_DELTA_CHECK = "net_delta_bounds"
_MULTILEG_CHECK = "multileg_consistency"


@dataclass(frozen=True)
class NetDeltaBounds:
    """The inclusive share-equivalent net-delta band a hedge must land in."""

    lower: float
    upper: float

    @classmethod
    def from_context(
        cls, hypothesis: StrategyHypothesis, context: HedgeContext
    ) -> NetDeltaBounds:
        """Derive the band from the shares held in the hedged names.

        Upper bound is the slop tolerance (a hedge should not be net-long).
        Lower bound is ``-(covered_shares + tolerance)`` (it should not hedge
        past the position). With no legs or no shares the band is symmetric at
        ``±tolerance``.
        """
        underlyings = {leg.underlying for leg in hypothesis.legs}
        shares = sum(
            abs(position.qty)
            for position in context.portfolio_state.positions
            if position.symbol in underlyings
            and position.asset_class is AssetClass.EQUITY
        )
        tolerance = max(
            DELTA_TOLERANCE_SHARES, _MARGIN_FRACTION * shares
        )
        return cls(lower=-(shares + tolerance), upper=tolerance)


def check_net_delta_bounds(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    bounds: NetDeltaBounds | None = None,
) -> CheckOutcome:
    """Fail when the proposal's net delta is outside the hedge band (P5-BE-5).

    A missing ``hedge_metrics.net_delta`` is treated as "not evaluated" and
    passes, mirroring how :func:`check_max_hedge_ratio` handles a missing ratio.
    Exactly on either bound passes.
    """
    band = bounds or NetDeltaBounds.from_context(hypothesis, context)
    net_delta = hypothesis.hedge_metrics.net_delta

    if net_delta is None:
        return CheckOutcome(
            name=_NET_DELTA_CHECK,
            category=_OPTIONS,
            passed=True,
            detail="net delta not computed — nothing to bound",
        )

    if band.lower <= net_delta <= band.upper:
        return CheckOutcome(
            name=_NET_DELTA_CHECK,
            category=_OPTIONS,
            passed=True,
            detail=(
                f"net delta {net_delta:,.1f} within band "
                f"[{band.lower:,.1f}, {band.upper:,.1f}]"
            ),
            observed=net_delta,
        )

    breached = band.upper if net_delta > band.upper else band.lower
    side = "adds net-long exposure" if net_delta > band.upper else "over-hedges"
    return CheckOutcome(
        name=_NET_DELTA_CHECK,
        category=_OPTIONS,
        passed=False,
        code=ViolationCode.NET_DELTA_OUT_OF_BOUNDS,
        detail=(
            f"net delta {net_delta:,.1f} {side} — outside band "
            f"[{band.lower:,.1f}, {band.upper:,.1f}]"
        ),
        observed=net_delta,
        limit=breached,
    )


def _fail_multileg(detail: str) -> CheckOutcome:
    return CheckOutcome(
        name=_MULTILEG_CHECK,
        category=_OPTIONS,
        passed=False,
        code=ViolationCode.MULTILEG_INCONSISTENT,
        detail=detail,
    )


def _pass_multileg(detail: str) -> CheckOutcome:
    return CheckOutcome(
        name=_MULTILEG_CHECK, category=_OPTIONS, passed=True, detail=detail
    )


def _one(legs: list[OptionLeg], right: OptionRight, side: OrderSide) -> OptionLeg | None:
    matches = [
        leg for leg in legs if leg.right is right and leg.side is side
    ]
    return matches[0] if len(matches) == 1 else None


def check_multileg_consistency(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
) -> CheckOutcome:
    """Fail when a multi-leg structure is internally inconsistent (P5-BE-5).

    Rejections: legs spanning more than one underlying; a ``NO_HEDGE`` carrying
    legs; a ``COLLAR`` missing its long put or short call, or with the put
    struck at/above the call; a ``PUT_SPREAD`` that is not two puts with one
    bought and one sold, or whose long strike is not above the short strike
    (inverted). ``context`` is accepted for call-site symmetry.
    """
    del context  # consistency is intrinsic to the legs
    legs = hypothesis.legs

    if not legs:
        if hypothesis.strategy is StrategyType.NO_HEDGE:
            return _pass_multileg("no-hedge proposal carries no legs, as expected")
        return _pass_multileg("no legs to cross-check")

    if hypothesis.strategy is StrategyType.NO_HEDGE:
        return _fail_multileg(
            f"NO_HEDGE proposal carries {len(legs)} leg(s)"
        )

    underlyings = {leg.underlying for leg in legs}
    if len(underlyings) > 1:
        return _fail_multileg(
            f"legs span multiple underlyings: {sorted(underlyings)}"
        )

    if hypothesis.strategy is StrategyType.PUT_SPREAD:
        long_put = _one(legs, OptionRight.PUT, OrderSide.BUY)
        short_put = _one(legs, OptionRight.PUT, OrderSide.SELL)
        if len(legs) != 2 or long_put is None or short_put is None:
            return _fail_multileg(
                "put spread must be exactly one long put and one short put"
            )
        if long_put.strike <= short_put.strike:
            return _fail_multileg(
                f"put-spread strikes inverted: long {long_put.strike:g} is not "
                f"above short {short_put.strike:g}"
            )
        return _pass_multileg(
            f"put spread long {long_put.strike:g} / short {short_put.strike:g}"
        )

    if hypothesis.strategy is StrategyType.COLLAR:
        long_put = _one(legs, OptionRight.PUT, OrderSide.BUY)
        short_call = _one(legs, OptionRight.CALL, OrderSide.SELL)
        if long_put is None or short_call is None:
            missing = "long put" if long_put is None else "short call"
            return _fail_multileg(f"collar is missing its {missing}")
        if long_put.strike >= short_call.strike:
            return _fail_multileg(
                f"collar strikes inverted: put {long_put.strike:g} is not "
                f"below call {short_call.strike:g}"
            )
        return _pass_multileg(
            f"collar put {long_put.strike:g} / call {short_call.strike:g}"
        )

    return _pass_multileg(
        f"{hypothesis.strategy.value} legs are internally consistent"
    )
