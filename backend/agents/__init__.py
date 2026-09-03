"""Analysis-agent layer — Phase 3 (BRD §12–14).

The context builder (P3-BE-4) is the first piece: it turns the full per-cycle
:class:`~backend.agents.context_builder.AnalysisInputs` bundle into one small,
task-relevant slice per analysis agent, so no agent's prompt is diluted with
data it does not need.
"""

from __future__ import annotations

from backend.agents.assembler import (
    AGENT_TO_SECTION,
    ANALYSIS_AGENT_FNS,
    assemble_hedge_context,
)
from backend.agents.base import AgentError
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
from backend.agents.market import analyze_market
from backend.agents.news import analyze_news
from backend.agents.options import analyze_options
from backend.agents.portfolio import analyze_portfolio
from backend.agents.stock import analyze_stocks

__all__ = [
    "AGENT_TO_SECTION",
    "ANALYSIS_AGENTS",
    "ANALYSIS_AGENT_FNS",
    "AgentContextSlice",
    "AgentError",
    "AnalysisInputs",
    "MarketData",
    "OptionChain",
    "OptionQuoteRow",
    "RawNewsArticle",
    "SymbolBar",
    "analyze_market",
    "analyze_news",
    "analyze_options",
    "analyze_portfolio",
    "analyze_stocks",
    "assemble_hedge_context",
    "build_agent_contexts",
    "carries_full_portfolio",
    "log_agent_context_sizes",
]
