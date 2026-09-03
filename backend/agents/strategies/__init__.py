"""Strategy-agent layer — Phase 4 (BRD §15–18).

The four hedge-family agents share one shape: consume the assembled
:class:`~backend.models.hedge_context.HedgeContext`, emit one
:class:`~backend.models.strategy.StrategyHypothesis` — viable, or a first-class
rejection of the family. :class:`StrategyAgent` (P4-BE-1) is that base class;
:class:`ProtectivePutAgent`, :class:`PutSpreadAgent`, :class:`CollarAgent` and
:class:`NoHedgeAgent` (P4-BE-2..5) are the concrete families.
:class:`StrategyManager` (P4-BE-7/8/9) converts surviving hypotheses into a
:class:`~backend.models.strategy.StrategyDecision`.
"""

from __future__ import annotations

from backend.agents.strategies.base import SelfRejection, StrategyAgent
from backend.agents.strategies.collar import CollarAgent
from backend.agents.strategies.manager import StrategyManager
from backend.agents.strategies.no_hedge import NoHedgeAgent
from backend.agents.strategies.prefilter import (
    DroppedHypothesis,
    PrefilterLimits,
    PrefilterResult,
    prefilter,
)
from backend.agents.strategies.protective_put import ProtectivePutAgent
from backend.agents.strategies.put_spread import PutSpreadAgent

__all__ = [
    "SelfRejection",
    "StrategyAgent",
    "ProtectivePutAgent",
    "PutSpreadAgent",
    "CollarAgent",
    "NoHedgeAgent",
    "StrategyManager",
    "prefilter",
    "PrefilterLimits",
    "PrefilterResult",
    "DroppedHypothesis",
]
