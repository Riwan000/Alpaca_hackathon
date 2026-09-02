"""Black-Scholes-Merton European option price and greeks (P2-BE-9).

Pure and dependency-free: the standard-normal CDF is built from :func:`math.erf`,
so the quant layer keeps its "no NumPy / no SciPy" footprint. Notation follows
Hull, *Options, Futures, and Other Derivatives*::

    S  spot price             sigma  volatility, annualised (e.g. 0.20)
    K  strike price            r      continuously-compounded risk-free rate
    T  time to expiry (years)  q      continuous dividend / carry yield

    d1 = (ln(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

Greek conventions (documented because they are the usual source of confusion):

* ``delta`` — d price / d S.
* ``gamma`` — d2 price / d S2; identical for a call and a put.
* ``vega``  — d price / d sigma, per **1.00** of volatility. Divide by 100 for
  the move per volatility *point*. Identical for a call and a put.
* ``theta`` — d price / d t, per **year**. Divide by :data:`DAYS_PER_YEAR` for
  the per-calendar-day decay.

``S``, ``K``, ``T`` and ``sigma`` must all be strictly positive; an expired or
otherwise degenerate contract is the caller's responsibility to special-case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from backend.quant.helpers import CALENDAR_DAYS_PER_YEAR

__all__ = [
    "OptionKind",
    "Greeks",
    "DAYS_PER_YEAR",
    "to_option_kind",
    "d1_d2",
    "bs_price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "black_scholes",
]

_SQRT_2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

#: Backward-compatible alias — the canonical name lives in :mod:`backend.quant.helpers`.
DAYS_PER_YEAR: float = CALENDAR_DAYS_PER_YEAR


class OptionKind(str, Enum):
    """Right of a vanilla option contract."""

    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class Greeks:
    """Black-Scholes price and its first/second-order sensitivities.

    ``vega`` is quoted per 1.00 of volatility and ``theta`` per year — see the
    module docstring.
    """

    price: float
    delta: float
    gamma: float
    vega: float
    theta: float


def to_option_kind(kind: OptionKind | str) -> OptionKind:
    """Coerce a loose call/put value to :class:`OptionKind`.

    Accepts an :class:`OptionKind`, a ``"call"`` / ``"put"`` string (any case),
    or any other ``str`` enum whose value is one of those — so a wire enum from
    ``backend.models`` maps cleanly without the quant layer importing it.
    """
    if isinstance(kind, OptionKind):
        return kind
    raw = kind.value if isinstance(kind, Enum) else kind
    try:
        return OptionKind(str(raw).strip().upper())
    except ValueError:
        raise ValueError(f"kind must be a call or a put, got {kind!r}") from None


def _norm_cdf(x: float) -> float:
    """Standard-normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


def _norm_pdf(x: float) -> float:
    """Standard-normal probability density function."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def _require_positive(spot: float, strike: float, time_to_expiry: float, volatility: float) -> None:
    if spot <= 0:
        raise ValueError(f"spot must be positive, got {spot!r}")
    if strike <= 0:
        raise ValueError(f"strike must be positive, got {strike!r}")
    if time_to_expiry <= 0:
        raise ValueError(f"time_to_expiry must be positive, got {time_to_expiry!r}")
    if volatility <= 0:
        raise ValueError(f"volatility must be positive, got {volatility!r}")


def d1_d2(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    dividend_yield: float = 0.0,
) -> tuple[float, float]:
    """The Black-Scholes ``d1`` and ``d2`` terms."""
    _require_positive(spot, strike, time_to_expiry, volatility)
    vol_sqrt_t = volatility * math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def _terms(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    dividend_yield: float,
) -> tuple[float, float, float, float]:
    """``(d1, d2, discount, carry)`` where ``discount = e^-rT``, ``carry = e^-qT``."""
    d1, d2 = d1_d2(spot, strike, time_to_expiry, volatility, rate, dividend_yield)
    discount = math.exp(-rate * time_to_expiry)
    carry = math.exp(-dividend_yield * time_to_expiry)
    return d1, d2, discount, carry


def bs_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    kind: OptionKind | str,
    dividend_yield: float = 0.0,
) -> float:
    """Black-Scholes-Merton price of a European call or put."""
    option = to_option_kind(kind)
    d1, d2, discount, carry = _terms(
        spot, strike, time_to_expiry, volatility, rate, dividend_yield
    )
    if option is OptionKind.CALL:
        return spot * carry * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * carry * _norm_cdf(-d1)


def delta(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    kind: OptionKind | str,
    dividend_yield: float = 0.0,
) -> float:
    """d price / d spot. Call in ``(0, 1)``; put in ``(-1, 0)``."""
    option = to_option_kind(kind)
    d1, _, _, carry = _terms(
        spot, strike, time_to_expiry, volatility, rate, dividend_yield
    )
    if option is OptionKind.CALL:
        return carry * _norm_cdf(d1)
    return carry * (_norm_cdf(d1) - 1.0)


def gamma(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """d2 price / d spot2 — identical for a call and a put."""
    d1, _, _, carry = _terms(
        spot, strike, time_to_expiry, volatility, rate, dividend_yield
    )
    return carry * _norm_pdf(d1) / (spot * volatility * math.sqrt(time_to_expiry))


def vega(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """d price / d volatility, per 1.00 of vol — identical for a call and a put."""
    d1, _, _, carry = _terms(
        spot, strike, time_to_expiry, volatility, rate, dividend_yield
    )
    return spot * carry * _norm_pdf(d1) * math.sqrt(time_to_expiry)


def theta(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    kind: OptionKind | str,
    dividend_yield: float = 0.0,
) -> float:
    """d price / d t, per year (typically negative — time decay)."""
    option = to_option_kind(kind)
    d1, d2, discount, carry = _terms(
        spot, strike, time_to_expiry, volatility, rate, dividend_yield
    )
    decay = -(spot * carry * _norm_pdf(d1) * volatility) / (2.0 * math.sqrt(time_to_expiry))
    if option is OptionKind.CALL:
        return (
            decay
            - rate * strike * discount * _norm_cdf(d2)
            + dividend_yield * spot * carry * _norm_cdf(d1)
        )
    return (
        decay
        + rate * strike * discount * _norm_cdf(-d2)
        - dividend_yield * spot * carry * _norm_cdf(-d1)
    )


def black_scholes(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
    kind: OptionKind | str,
    dividend_yield: float = 0.0,
) -> Greeks:
    """Price plus delta, gamma, vega and theta in a single :class:`Greeks`."""
    option = to_option_kind(kind)
    args = (spot, strike, time_to_expiry, volatility, rate)
    return Greeks(
        price=bs_price(*args, option, dividend_yield),
        delta=delta(*args, option, dividend_yield),
        gamma=gamma(*args, dividend_yield),
        vega=vega(*args, dividend_yield),
        theta=theta(*args, option, dividend_yield),
    )
