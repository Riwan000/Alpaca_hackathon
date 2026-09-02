"""Deterministic portfolio metrics — Phase 2 (tasks P2-BE-1 … P2-BE-4).

Pure functions over an in-memory :class:`Position` list or an equity curve: no
LLM, no I/O. Downstream agents reason about these numbers as the source of
truth (BRD §10).
"""

from __future__ import annotations

from backend.quant.portfolio.concentration import (
    Concentration,
    compute_concentration,
    effective_holdings,
    hhi,
    top_n_weight,
    weights,
)
from backend.quant.portfolio.drawdown import (
    DrawdownPoint,
    DrawdownResult,
    compute_drawdown,
    drawdown_series,
    high_water_marks,
    max_drawdown,
)
from backend.quant.portfolio.exposure import (
    ExposureBreakdown,
    PositionExposure,
    compute_exposure,
    gross_exposure,
    net_exposure,
    position_exposure,
)
from backend.quant.portfolio.position import (
    Position,
    gross_notional,
    signed_notional,
)
from backend.quant.portfolio.value import (
    PortfolioValue,
    compute_portfolio_value,
    portfolio_value,
    positions_value,
)

__all__ = [
    # position primitive
    "Position",
    "signed_notional",
    "gross_notional",
    # value
    "PortfolioValue",
    "compute_portfolio_value",
    "portfolio_value",
    "positions_value",
    # exposure
    "PositionExposure",
    "ExposureBreakdown",
    "position_exposure",
    "compute_exposure",
    "gross_exposure",
    "net_exposure",
    # concentration
    "Concentration",
    "weights",
    "hhi",
    "effective_holdings",
    "top_n_weight",
    "compute_concentration",
    # drawdown
    "DrawdownPoint",
    "DrawdownResult",
    "high_water_marks",
    "drawdown_series",
    "max_drawdown",
    "compute_drawdown",
]
