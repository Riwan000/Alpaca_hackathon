"""Strategy-agent layer — Phase 4 (BRD §15–18).

The four hedge-family agents share one shape: consume the assembled
:class:`~backend.models.hedge_context.HedgeContext`, emit one
:class:`~backend.models.strategy.StrategyHypothesis` — viable, or a first-class
rejection of the family. :class:`StrategyAgent` (P4-BE-1) is that base class;
:class:`ProtectivePutAgent`, :class:`PutSpreadAgent`, :class:`CollarAgent` and
:class:`NoHedgeAgent` (P4-BE-2..5) are the concrete families.
"""

from __future__ import annotations

from backend.agents.strategies.base import SelfRejection, StrategyAgent
from backend.agents.strategies.collar import CollarAgent
from backend.agents.strategies.no_hedge import NoHedgeAgent
from backend.agents.strategies.protective_put import ProtectivePutAgent
from backend.agents.strategies.put_spread import PutSpreadAgent

__all__ = [
    "SelfRejection",
    "StrategyAgent",
    "ProtectivePutAgent",
    "PutSpreadAgent",
    "CollarAgent",
    "NoHedgeAgent",
]
