"""Analysis-agent layer — Phase 3 (BRD §12–14).

The context builder (P3-BE-4) is the first piece: it turns the full per-cycle
:class:`~backend.agents.context_builder.AnalysisInputs` bundle into one small,
task-relevant slice per analysis agent, so no agent's prompt is diluted with
data it does not need.
"""

from __future__ import annotations

from backend.agents.context_builder import (
    ANALYSIS_AGENTS,
    AgentContextSlice,
    AnalysisInputs,
    MarketData,
    OptionChain,
    OptionQuoteRow,
    RawNewsArticle,
    SymbolBar,
    build_agent_contexts,
    carries_full_portfolio,
    log_agent_context_sizes,
)

__all__ = [
    "ANALYSIS_AGENTS",
    "AgentContextSlice",
    "AnalysisInputs",
    "MarketData",
    "OptionChain",
    "OptionQuoteRow",
    "RawNewsArticle",
    "SymbolBar",
    "build_agent_contexts",
    "carries_full_portfolio",
    "log_agent_context_sizes",
]
