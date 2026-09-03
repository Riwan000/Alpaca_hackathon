"""``HedgeContext`` assembler — tasks P3-BE-10 / P3-BE-11 (BRD §14, §31).

Runs the five Phase 3 analysis agents over one
:class:`~backend.agents.context_builder.AnalysisInputs` bundle and merges their
outputs into a single :class:`~backend.models.hedge_context.HedgeContext`.

The pass is **degradation-tolerant** (BRD §31 — "continue with degraded context
and clearly record the limitation"): if an agent raises — an
:class:`~backend.agents.base.AgentError`, a ``ValidationError`` on its slice, or
anything else — the assembler logs it, leaves that section at its safe default,
records the section name in ``HedgeContext.degraded_sections`` and carries on. A
run therefore always returns a schema-valid ``HedgeContext``; a killed agent
shows up as a ``degraded`` marker, never a crash.

``cycle_id`` / ``timestamp`` / ``objective`` / ``current_hedge`` are copied
straight from the inputs. Every agent-populated section has an empty default
(``[]`` / ``None``) except ``portfolio_state``, which is required with no default
— if the Portfolio agent fails, the raw pre-enrichment snapshot from the inputs
is used so the field is still populated (still marked degraded, since exposure /
HHI / drawdown were not recomputed).

**Run logging (P3-BE-11).** Pass ``run_repo`` — anything with the
:class:`AgentRunSink` shape, in practice
:class:`~backend.db.agent_runs_repo.AgentRunRepository` — and every agent
invocation writes exactly one ``agent_runs`` row: ``create`` when it starts
(``inputs`` = that agent's context slice), then ``finish`` when it returns, with
``outputs`` on success or ``error`` on failure and the measured ``duration_ms``.
Row order matches ``ANALYSIS_AGENTS`` order. Logging never changes the pass
outcome: a repository error while recording a run is swallowed (warned) so the
context is still assembled.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel

from backend.agents.context_builder import (
    ANALYSIS_AGENTS,
    AgentContextSlice,
    AnalysisInputs,
    build_agent_contexts,
)
from backend.agents.market import analyze_market
from backend.agents.news import analyze_news
from backend.agents.options import analyze_options
from backend.agents.portfolio import analyze_portfolio
from backend.agents.stock import analyze_stocks
from backend.db.agent_runs_repo import AgentRunRecord
from backend.models.hedge_context import HedgeContext, PortfolioState

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_TO_SECTION",
    "ANALYSIS_AGENT_FNS",
    "AgentRunSink",
    "AnalysisAgentFn",
    "assemble_hedge_context",
]

#: One analysis agent — a context slice (+ optional LLM client) → its context section.
AnalysisAgentFn = Callable[..., Any]

#: The Phase 3 analysis agents keyed by their slice name (BRD §12–13).
ANALYSIS_AGENT_FNS: dict[str, AnalysisAgentFn] = {
    "portfolio": analyze_portfolio,
    "stock": analyze_stocks,
    "market": analyze_market,
    "news": analyze_news,
    "options": analyze_options,
}

#: Agent slice name → the ``HedgeContext`` field that agent populates.
AGENT_TO_SECTION: dict[str, str] = {
    "portfolio": "portfolio_state",
    "stock": "stock_state",
    "market": "market_state",
    "news": "news_context",
    "options": "option_candidates",
}

#: Empty defaults for the agent-populated sections (``portfolio_state`` is
#: special — see the module docstring).
_SECTION_DEFAULTS: dict[str, Any] = {
    "stock_state": [],
    "market_state": None,
    "news_context": [],
    "option_candidates": [],
}


class AgentRunSink(Protocol):
    """The slice of :class:`~backend.db.agent_runs_repo.AgentRunRepository` the
    assembler needs to record one row per agent (task P3-BE-11)."""

    def create(self, record: AgentRunRecord) -> AgentRunRecord: ...

    def finish(
        self,
        run_id: int,
        *,
        duration_ms: int,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AgentRunRecord: ...


def _jsonify(value: Any) -> Any:
    """Best-effort JSON-safe form of an agent output for the ``outputs`` column."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonify(v) for k, v in value.items()}
    return value


def _outputs_row(section: str, value: Any) -> dict[str, Any]:
    """Wrap an agent's return value as the ``agent_runs.outputs`` jsonb payload."""
    return {section: _jsonify(value)}


def _record_start(
    run_repo: AgentRunSink, cycle_id: str, agent: str, agent_slice: AgentContextSlice
) -> int | None:
    """Write the *started* ``agent_runs`` row; return its id (``None`` on failure)."""
    try:
        created = run_repo.create(
            AgentRunRecord(
                cycle_id=cycle_id,
                agent_name=agent,
                inputs=dict(agent_slice.payload),
            )
        )
        return created.id
    except Exception:  # noqa: BLE001 - run logging must never break the pass
        logger.warning("could not open an agent_runs row for %r", agent, exc_info=True)
        return None


def _record_finish(
    run_repo: AgentRunSink,
    run_id: int | None,
    *,
    duration_ms: int,
    section: str,
    value: Any = None,
    error: str | None = None,
) -> None:
    """Close the ``agent_runs`` row opened by :func:`_record_start` (best effort)."""
    if run_id is None:
        return
    try:
        if error is None:
            run_repo.finish(
                run_id, duration_ms=duration_ms, outputs=_outputs_row(section, value)
            )
        else:
            run_repo.finish(run_id, duration_ms=duration_ms, error=error)
    except Exception:  # noqa: BLE001 - run logging must never break the pass
        logger.warning("could not close agent_runs row %s", run_id, exc_info=True)


def assemble_hedge_context(
    inputs: AnalysisInputs,
    *,
    client: OpenAI | None = None,
    agent_fns: Mapping[str, AnalysisAgentFn] | None = None,
    run_repo: AgentRunSink | None = None,
) -> HedgeContext:
    """Run the analysis agents over ``inputs`` and merge them into a ``HedgeContext``.

    A failing agent degrades its section instead of aborting the pass: the section
    name lands in ``degraded_sections`` and the run still returns a schema-valid
    context (BRD §31). ``agent_fns`` overrides the callable used for a slice —
    pass one that raises to exercise the degraded path. ``run_repo`` (task
    P3-BE-11) records one ``agent_runs`` row per agent with timing.
    """
    fns = agent_fns or ANALYSIS_AGENT_FNS
    slices = build_agent_contexts(inputs)

    sections: dict[str, Any] = {}
    degraded: list[str] = []
    for agent in ANALYSIS_AGENTS:
        section = AGENT_TO_SECTION[agent]
        run_id = (
            _record_start(run_repo, inputs.cycle_id, agent, slices[agent])
            if run_repo is not None
            else None
        )
        started = time.perf_counter()
        try:
            value = fns[agent](slices[agent], client=client)
        except Exception as exc:  # noqa: BLE001 - any agent failure degrades its section, never the pass
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "analysis agent %r failed; section %r degraded", agent, section,
                exc_info=True,
            )
            degraded.append(section)
            if run_repo is not None:
                _record_finish(
                    run_repo, run_id, duration_ms=elapsed_ms, section=section,
                    error=f"{type(exc).__name__}: {exc}",
                )
            continue
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        sections[section] = value
        if run_repo is not None:
            _record_finish(
                run_repo, run_id, duration_ms=elapsed_ms, section=section, value=value
            )

    portfolio_state = sections.get("portfolio_state")
    if not isinstance(portfolio_state, PortfolioState):
        portfolio_state = inputs.portfolio_state

    return HedgeContext(
        cycle_id=inputs.cycle_id,
        timestamp=inputs.timestamp,
        objective=inputs.objective,
        current_hedge=inputs.current_hedge,
        portfolio_state=portfolio_state,
        market_state=sections.get("market_state", _SECTION_DEFAULTS["market_state"]),
        stock_state=sections.get("stock_state") or [],
        news_context=sections.get("news_context") or [],
        option_candidates=sections.get("option_candidates") or [],
        degraded_sections=degraded,
    )
