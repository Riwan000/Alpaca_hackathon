"""Options Analysis Agent — task P3-BE-9 (BRD §13).

A deterministic filter over the raw option chains in the Options context slice —
no LLM. Each quote must clear three gates before it becomes an
:class:`~backend.models.hedge_context.OptionCandidate`:

* **liquidity** — open interest ≥ ``min_open_interest``;
* **spread** — a two-sided market with relative spread ``(ask-bid)/mid`` ≤
  ``max_rel_spread``;
* **expiry window** — days to expiry within ``[min_days_to_expiry,
  max_days_to_expiry]``.

Survivors are ranked by open interest and capped per underlying. ``premium`` is
the bid/ask mid; the implied vol on each row is carried through so the Strategy
layer sees the IV surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from openai import OpenAI
from pydantic import Field

from backend.agents.context_builder import AgentContextSlice
from backend.models.common import Contract
from backend.models.enums import OptionRight
from backend.models.hedge_context import OptionCandidate

__all__ = ["OptionsAgentInput", "OptionsFilterConfig", "analyze_options"]

_HIGH_OI_FACTOR = 5
_TIGHT_SPREAD = 0.05
_LIQUIDITY_HIGH = "high"
_LIQUIDITY_OK = "ok"


@dataclass(frozen=True)
class OptionsFilterConfig:
    """Thresholds the Options agent filters a chain against."""

    min_open_interest: int = 100
    max_rel_spread: float = 0.25
    min_days_to_expiry: int = 7
    max_days_to_expiry: int = 90
    max_candidates_per_underlying: int = 6


class _Quote(Contract):
    right: OptionRight
    strike: float
    expiration: date
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    iv: float | None = None
    delta: float | None = None


class _Chain(Contract):
    underlying: str
    spot: float | None = None
    quotes: list[_Quote] = Field(default_factory=list)


class OptionsAgentInput(Contract):
    """The Options agent's validated view of its context slice."""

    cycle_id: str
    timestamp: datetime
    hedge_underlyings: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    portfolio_value: float | None = None
    option_chains: list[_Chain] = Field(default_factory=list)


def _two_sided(quote: _Quote) -> tuple[float, float] | None:
    if quote.bid is None or quote.ask is None:
        return None
    if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        return None
    mid = (quote.bid + quote.ask) / 2.0
    return mid, (quote.ask - quote.bid) / mid


def _candidate(
    chain: _Chain, quote: _Quote, cfg: OptionsFilterConfig, today: date
) -> OptionCandidate | None:
    if quote.open_interest is None or quote.open_interest < cfg.min_open_interest:
        return None
    dte = (quote.expiration - today).days
    if dte < cfg.min_days_to_expiry or dte > cfg.max_days_to_expiry:
        return None
    market = _two_sided(quote)
    if market is None:
        return None
    mid, rel_spread = market
    if rel_spread > cfg.max_rel_spread:
        return None
    high = quote.open_interest >= cfg.min_open_interest * _HIGH_OI_FACTOR or rel_spread <= _TIGHT_SPREAD
    return OptionCandidate(
        underlying=chain.underlying,
        right=quote.right,
        strike=quote.strike,
        expiration=quote.expiration,
        premium=mid,
        bid=quote.bid,
        ask=quote.ask,
        volume=quote.volume,
        open_interest=quote.open_interest,
        iv=quote.iv,
        delta=quote.delta,
        liquidity=_LIQUIDITY_HIGH if high else _LIQUIDITY_OK,
    )


def analyze_options(
    ctx: AgentContextSlice,
    *,
    client: OpenAI | None = None,  # noqa: ARG001 - deterministic agent, kept for a uniform call site
    config: OptionsFilterConfig | None = None,
    now: datetime | None = None,
) -> list[OptionCandidate]:
    """Return the liquidity-filtered ``option_candidates`` for ``ctx`` (BRD §13)."""
    data = OptionsAgentInput.model_validate(dict(ctx.payload))
    cfg = config or OptionsFilterConfig()
    today = (now or datetime.now(timezone.utc)).date()
    wanted = {s.strip().upper() for s in data.hedge_underlyings}

    out: list[OptionCandidate] = []
    for chain in data.option_chains:
        if wanted and chain.underlying.strip().upper() not in wanted:
            continue
        found = [
            cand
            for quote in chain.quotes
            if (cand := _candidate(chain, quote, cfg, today)) is not None
        ]
        found.sort(key=lambda c: (-(c.open_interest or 0), c.expiration))
        out.extend(found[: cfg.max_candidates_per_underlying])
    return out
