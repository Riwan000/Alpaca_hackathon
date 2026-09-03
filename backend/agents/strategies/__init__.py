"""Strategy-agent layer — Phase 4 (BRD §15–18).

The four hedge-family agents (P4-BE-2..5) share one shape: consume the assembled
:class:`~backend.models.hedge_context.HedgeContext`, emit one
:class:`~backend.models.strategy.StrategyHypothesis` — viable, or a first-class
rejection of the family. :class:`StrategyAgent` (P4-BE-1) is that base class.
"""

from __future__ import annotations

from backend.agents.strategies.base import SelfRejection, StrategyAgent

__all__ = ["SelfRejection", "StrategyAgent"]
