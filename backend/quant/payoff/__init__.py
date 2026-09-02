"""Deterministic payoff analytics — Phase 2 (tasks P2-BE-11 … P2-BE-13).

Pure functions over in-memory legs: premium cost as a fraction of the book,
expiration payoff curves, and worst-case / breakeven analysis for multi-leg
hedge structures. No LLM, no I/O, no NumPy/SciPy.
"""

from __future__ import annotations

from backend.quant.payoff.curve import (
    OPTION_MULTIPLIER,
    LegKind,
    PayoffLeg,
    PayoffPoint,
    leg_entry_debit,
    leg_intrinsic,
    leg_payoff,
    payoff_curve,
    to_leg_kind,
    total_payoff,
)
from backend.quant.payoff.max_loss import (
    StructureRisk,
    breakevens,
    max_loss,
    max_profit,
    structure_risk,
    tail_slopes,
)
from backend.quant.payoff.premium import (
    PremiumCost,
    PremiumLeg,
    cost_fraction,
    hedge_cost,
    net_premium_cash,
    premium_cash,
    premium_cost,
)

__all__ = [
    # premium
    "PremiumCost",
    "PremiumLeg",
    "premium_cash",
    "cost_fraction",
    "premium_cost",
    "net_premium_cash",
    "hedge_cost",
    # curve
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
    # max loss / breakevens
    "StructureRisk",
    "tail_slopes",
    "structure_risk",
    "max_loss",
    "max_profit",
    "breakevens",
]
