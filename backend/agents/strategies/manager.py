"""Strategy Manager — tasks P4-BE-7/8/9 (BRD §17–18).

The Strategy Manager sits after the pre-filter and converts the surviving
hypotheses into a :class:`~backend.models.strategy.StrategyDecision`.  It works
in three sequential stages that the tests target individually:

**Stage 1 — validate** (P4-BE-7)
    Strip schema-invalid hypotheses, short-circuit to ``NO_TRADE`` when every
    remaining hypothesis is ``NOT_VIABLE`` (nothing to trade).

**Stage 2 — compare** (P4-BE-8)
    Build one :class:`~backend.models.strategy.ComparisonRow` per *viable*
    hypothesis from quant fields already on the hypothesis.  No LLM involved.

**Stage 3 — select** (P4-BE-9)
    Ask the LLM to pick the best strategy and cite the winning metric.  A
    deterministic fallback (lowest-cost non-NO_HEDGE viable hypothesis) fires
    whenever the LLM is unavailable, times out, or returns unparsable output.
    A degraded context (``context.degraded_sections`` non-empty) or an explicit
    low-confidence signal from the LLM produces a ``REASSESS`` decision.

:meth:`StrategyManager.run` chains all three and is what ``POST /strategy/evaluate``
will call (P4-BE-11).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from backend.agents.prompts import render as render_prompt
from backend.llm.provider import get_llm_client, resolve_model
from backend.models.enums import DecisionType, HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import (
    ComparisonRow,
    StrategyDecision,
    StrategyHypothesis,
)

from .prefilter import PrefilterResult

__all__ = ["StrategyManager"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# prompt template (Stage 3)
# ---------------------------------------------------------------------------
#
# The system prompt and the closing instruction live in
# ``backend/agents/prompts/templates.yaml`` under the ``manager`` key (P4-BE-10);
# :func:`_build_context_block` produces the ``{context_block}`` the template wraps.

_MANAGER_TEMPLATE = "manager"

_LOW_CONFIDENCE_THRESHOLD: float = 0.5

_FALLBACK_RATIONALE_PREFIX = (
    "Deterministic fallback (LLM unavailable): selected the lowest-cost "
    "option hedge strategy within portfolio limits."
)


def _build_context_block(
    context: HedgeContext,
    viable: list[StrategyHypothesis],
    comparison: list[ComparisonRow],
    not_viable: list[StrategyHypothesis],
) -> str:
    """Render the ``{context_block}`` the ``manager`` template wraps.

    The portfolio context, comparison table, rejected strategies and per-strategy
    rationales; the decision instruction itself is in ``templates.yaml``.
    """
    portfolio = context.portfolio_state
    objective = context.objective

    parts: list[str] = []
    parts.append("=== Portfolio Context ===")
    parts.append(f"Total value:  ${portfolio.total_value:,.0f}")
    parts.append(f"Drawdown:     {portfolio.drawdown or 0:.1%}")
    parts.append(f"Volatility:   {portfolio.volatility or 0:.1%}")
    parts.append(
        f"Market regime: {context.market_state.regime if context.market_state else 'unknown'}"
    )
    parts.append(f"Drawdown tolerance: {objective.drawdown_tolerance_pct:.1%}")
    parts.append(f"Hedge budget (max): {objective.max_hedge_budget_pct:.1%} of portfolio")
    if context.degraded_sections:
        parts.append(
            f"⚠ Degraded analysis sections: {', '.join(context.degraded_sections)}"
        )
    parts.append("")

    parts.append("=== Viable Strategies (comparison table) ===")
    for row in comparison:
        metrics: list[str] = [f"strategy={row.strategy.value}", f"cost=${row.cost:,.0f}"]
        if row.downside_protection_pct is not None:
            metrics.append(f"downside_protection={row.downside_protection_pct:.1%}")
        if row.upside_giveup_pct is not None:
            metrics.append(f"upside_giveup={row.upside_giveup_pct:.1%}")
        if row.liquidity:
            metrics.append(f"liquidity={row.liquidity}")
        parts.append("  " + " | ".join(metrics))
    parts.append("")

    if not_viable:
        parts.append("=== Rejected Strategies ===")
        for h in not_viable:
            parts.append(f"  {h.strategy.value}: {h.rejection_reason}")
        parts.append("")

    # include each viable hypothesis's own rationale for richer context
    parts.append("=== Strategy Rationales ===")
    for h in viable:
        parts.append(f"  [{h.strategy.value}] {h.rationale}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _parse_llm_response(text: str) -> dict[str, Any]:
    """Parse the LLM text into a dict; raises ``ValueError`` on failure."""
    text = text.strip()
    # strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    if "decision" not in data:
        raise ValueError("LLM response missing 'decision' key")
    if data["decision"] not in ("SELECT_STRATEGY", "NO_TRADE", "REASSESS"):
        raise ValueError(f"Unknown decision value: {data['decision']!r}")
    return data


def _fallback_decision(
    viable: list[StrategyHypothesis],
    context: HedgeContext,
    rationale_prefix: str = _FALLBACK_RATIONALE_PREFIX,
) -> StrategyDecision:
    """Deterministic fallback: lowest-cost non-NO_HEDGE viable hypothesis."""
    candidates = [h for h in viable if h.strategy is not StrategyType.NO_HEDGE]
    if candidates:
        winner = min(candidates, key=lambda h: h.cost)
        alternatives = [h for h in viable if h is not winner]
        return StrategyDecision(
            cycle_id=context.cycle_id,
            decision=DecisionType.SELECT_STRATEGY,
            selected_strategy=winner.strategy,
            selected_hypothesis=winner,
            alternatives=alternatives,
            rationale=(
                f"{rationale_prefix} {winner.strategy.value} costs "
                f"${winner.cost:,.0f} and provides downside protection."
            ),
            reassessment_conditions=winner.rejection_conditions,
        )
    # all viable are NO_HEDGE — just take it
    if viable:
        winner = viable[0]
        return StrategyDecision(
            cycle_id=context.cycle_id,
            decision=DecisionType.NO_TRADE,
            selected_strategy=None,
            selected_hypothesis=None,
            alternatives=viable,
            rationale=(
                f"{rationale_prefix} No option hedge passed the budget/limit "
                "gates; leaving the book unhedged."
            ),
            reassessment_conditions=winner.rejection_conditions,
        )
    return StrategyDecision(
        cycle_id=context.cycle_id,
        decision=DecisionType.NO_TRADE,
        selected_strategy=None,
        selected_hypothesis=None,
        alternatives=[],
        rationale="No viable hypothesis available; leaving the book unhedged.",
    )


# ---------------------------------------------------------------------------
# StrategyManager
# ---------------------------------------------------------------------------


class StrategyManager:
    """Three-stage Strategy Manager (P4-BE-7/8/9 — BRD §17–18).

    The manager orchestrates the final step of the strategy layer::

        pre_result = prefilter(hypotheses, context)
        manager    = StrategyManager()
        decision   = manager.run(pre_result, context)

    The three stages can be called independently for testing:

    * :meth:`validate`  — Stage 1 (P4-BE-7)
    * :meth:`compare`   — Stage 2 (P4-BE-8)
    * :meth:`select`    — Stage 3 (P4-BE-9)
    """

    def __init__(self, *, client: OpenAI | None = None) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    # Stage 1 — Validation (P4-BE-7 / issue #109)
    # ------------------------------------------------------------------ #

    def validate(
        self,
        hypotheses: list[StrategyHypothesis],
        context: HedgeContext,
    ) -> StrategyDecision | None:
        """Validate hypotheses and short-circuit if no trade is possible.

        Strips any hypothesis with a mismatched ``cycle_id`` (a wiring bug,
        logged as an error).  If every remaining hypothesis is ``NOT_VIABLE``
        — or the list is empty — returns a ``NO_TRADE`` :class:`StrategyDecision`
        immediately so the caller skips the LLM call.  Returns ``None`` when at
        least one viable hypothesis exists, signalling that comparison and
        selection should proceed.

        Args:
            hypotheses: The combined kept list from :class:`~.prefilter.PrefilterResult`.
            context:    The assembled :class:`~backend.models.hedge_context.HedgeContext`.

        Returns:
            A ``NO_TRADE`` decision, or ``None`` (proceed to compare/select).
        """
        valid: list[StrategyHypothesis] = []
        for h in hypotheses:
            if h.cycle_id != context.cycle_id:
                logger.error(
                    "StrategyManager.validate: dropping hypothesis %s — "
                    "cycle_id %r != context %r",
                    h.strategy.value,
                    h.cycle_id,
                    context.cycle_id,
                )
                continue
            valid.append(h)

        viable_count = sum(1 for h in valid if h.viable)
        if viable_count == 0:
            # Build a rationale from the NOT_VIABLE reasons
            reasons = [
                f"{h.strategy.value}: {h.rejection_reason}"
                for h in valid
                if not h.viable and h.rejection_reason
            ]
            if reasons:
                rationale = (
                    "All strategy families were rejected — no trade is appropriate. "
                    "Reasons: " + "; ".join(reasons) + "."
                )
            else:
                rationale = "No viable strategy hypothesis available; leaving the book unhedged."

            return StrategyDecision(
                cycle_id=context.cycle_id,
                decision=DecisionType.NO_TRADE,
                selected_strategy=None,
                selected_hypothesis=None,
                alternatives=valid,
                rationale=rationale,
            )

        return None  # proceed to compare + select

    # ------------------------------------------------------------------ #
    # Stage 2 — Comparison (P4-BE-8 / issue #110)
    # ------------------------------------------------------------------ #

    def compare(
        self,
        viable: list[StrategyHypothesis],
        context: HedgeContext,
    ) -> list[ComparisonRow]:
        """Build the comparison table for the LLM (and the UI).

        One :class:`~backend.models.strategy.ComparisonRow` per viable hypothesis,
        in input order.  All rows share the same metric keys so the frontend can
        render a consistent column table.  Numbers come from the hypothesis's
        :class:`~backend.models.strategy.HedgeMetrics`, never from the LLM.

        Args:
            viable:  Viable hypotheses that survived validation + pre-filter.
            context: Used to compute ``upside_giveup_pct`` for collars.

        Returns:
            A list of :class:`ComparisonRow` with one entry per viable hypothesis.
        """
        total_value = context.portfolio_state.total_value
        rows: list[ComparisonRow] = []
        for h in viable:
            m = h.hedge_metrics
            # upside_giveup is meaningful for collars (short call caps the upside)
            upside_giveup: float | None = None
            if h.strategy is StrategyType.COLLAR and m.net_delta is not None:
                # Approximation: a collar's net delta is < 1 due to short call;
                # give-up ≈ (1 − |net_delta| / contracts) expressed as portfolio %.
                # Use cost_pct instead when delta not available — it's a reasonable proxy.
                pass
            if h.strategy is StrategyType.COLLAR and total_value > 0 and h.cost == 0:
                upside_giveup = 0.0  # cost-neutral collar — no give-up on a net credit

            rows.append(
                ComparisonRow(
                    strategy=h.strategy,
                    cost=h.cost,
                    downside_protection_pct=m.downside_protection_pct,
                    upside_giveup_pct=upside_giveup,
                    liquidity=h.liquidity,
                    verdict=None,  # populated by select()
                    score=None,
                )
            )
        return rows

    # ------------------------------------------------------------------ #
    # Stage 3 — Selection (P4-BE-9 / issue #111)
    # ------------------------------------------------------------------ #

    def select(
        self,
        viable: list[StrategyHypothesis],
        comparison: list[ComparisonRow],
        not_viable: list[StrategyHypothesis],
        context: HedgeContext,
    ) -> StrategyDecision:
        """Contextual reasoning + selection — calls the LLM, falls back deterministically.

        The LLM receives the comparison table and the portfolio context and must return
        a JSON object with ``decision``, ``selected_strategy``, ``rationale``, and
        ``confidence`` keys.

        Fallback triggers (no LLM call / parse error / low confidence):
        - No ``api_key`` configured → deterministic fallback immediately.
        - Any exception during the LLM call → deterministic fallback.
        - ``confidence < 0.5`` → ``REASSESS``.
        - Non-empty ``context.degraded_sections`` → ``REASSESS`` override.

        Args:
            viable:      Viable hypotheses (guaranteed non-empty by validate()).
            comparison:  Rows produced by compare() for the same viable set.
            not_viable:  NOT_VIABLE hypotheses passed through the pre-filter.
            context:     The full hedge context.

        Returns:
            A :class:`StrategyDecision` with decision, rationale, and optional
            selected hypothesis.
        """
        # ---- try LLM path ----
        try:
            data = self._call_llm(viable, comparison, not_viable, context)
        except Exception as exc:
            logger.warning(
                "StrategyManager.select: LLM call failed (%s); using deterministic fallback",
                exc,
            )
            return _fallback_decision(viable, context)

        # ---- parse and validate LLM response ----
        try:
            parsed = _parse_llm_response(data)
        except ValueError as exc:
            logger.warning(
                "StrategyManager.select: unparsable LLM response (%s); using deterministic fallback",
                exc,
            )
            return _fallback_decision(viable, context)

        # ---- low-confidence / degraded context → REASSESS ----
        confidence: float = float(parsed.get("confidence", 1.0))
        rationale: str = str(parsed.get("rationale", ""))

        if context.degraded_sections:
            return StrategyDecision(
                cycle_id=context.cycle_id,
                decision=DecisionType.REASSESS,
                selected_strategy=None,
                selected_hypothesis=None,
                alternatives=viable,
                comparison=comparison,
                rationale=(
                    f"Degraded analysis sections ({', '.join(context.degraded_sections)}) "
                    "reduce confidence; reassessment required. " + rationale
                ).strip(),
                reassessment_conditions=[
                    f"re-run with complete analysis (missing: {', '.join(context.degraded_sections)})"
                ],
            )

        if confidence < _LOW_CONFIDENCE_THRESHOLD:
            return StrategyDecision(
                cycle_id=context.cycle_id,
                decision=DecisionType.REASSESS,
                selected_strategy=None,
                selected_hypothesis=None,
                alternatives=viable,
                comparison=comparison,
                rationale=(
                    f"Low confidence ({confidence:.0%}): {rationale}"
                ).strip(),
                reassessment_conditions=["re-evaluate after updated market data"],
            )

        # ---- build the final decision ----
        decision_str: str = parsed["decision"]
        selected_strategy_name: str | None = parsed.get("selected_strategy")

        if decision_str == "SELECT_STRATEGY":
            # Resolve the selected strategy type
            selected_type: StrategyType | None = None
            selected_hyp: StrategyHypothesis | None = None
            if selected_strategy_name:
                try:
                    selected_type = StrategyType(selected_strategy_name)
                except ValueError:
                    logger.warning(
                        "StrategyManager.select: LLM returned unknown strategy %r; falling back",
                        selected_strategy_name,
                    )
                    return _fallback_decision(viable, context, rationale_prefix=rationale)

                selected_hyp = next(
                    (h for h in viable if h.strategy is selected_type), None
                )
                if selected_hyp is None:
                    logger.warning(
                        "StrategyManager.select: LLM selected %r but it is not in viable set; falling back",
                        selected_strategy_name,
                    )
                    return _fallback_decision(viable, context, rationale_prefix=rationale)

            if selected_hyp is None:
                return _fallback_decision(viable, context, rationale_prefix=rationale)

            alternatives = [h for h in viable if h is not selected_hyp]
            return StrategyDecision(
                cycle_id=context.cycle_id,
                decision=DecisionType.SELECT_STRATEGY,
                selected_strategy=selected_type,
                selected_hypothesis=selected_hyp,
                alternatives=alternatives,
                comparison=comparison,
                rationale=rationale or f"Selected {selected_type.value} as the best hedge for this context.",
                reassessment_conditions=selected_hyp.rejection_conditions,
            )

        if decision_str == "REASSESS":
            return StrategyDecision(
                cycle_id=context.cycle_id,
                decision=DecisionType.REASSESS,
                selected_strategy=None,
                selected_hypothesis=None,
                alternatives=viable,
                comparison=comparison,
                rationale=rationale or "Reassessment required based on current context.",
                reassessment_conditions=["re-evaluate after updated market data"],
            )

        # NO_TRADE
        return StrategyDecision(
            cycle_id=context.cycle_id,
            decision=DecisionType.NO_TRADE,
            selected_strategy=None,
            selected_hypothesis=None,
            alternatives=viable,
            comparison=comparison,
            rationale=rationale or "No trade recommended for the current context.",
        )

    # ------------------------------------------------------------------ #
    # Top-level orchestrator
    # ------------------------------------------------------------------ #

    def run(
        self,
        prefilter_result: PrefilterResult,
        context: HedgeContext,
        *,
        client: OpenAI | None = None,
    ) -> StrategyDecision:
        """Chain all three stages and return the final :class:`StrategyDecision`.

        Args:
            prefilter_result: The result of :func:`~.prefilter.prefilter`.
            context:          The assembled :class:`~backend.models.hedge_context.HedgeContext`.
            client:           Optional LLM client override (for testing).
        """
        if client is not None:
            self._client = client

        all_hypotheses = list(prefilter_result.kept)
        not_viable = [h for h in all_hypotheses if not h.viable]
        viable = [h for h in all_hypotheses if h.viable]

        # Stage 1
        early_exit = self.validate(all_hypotheses, context)
        if early_exit is not None:
            dropped_alternatives = [d.hypothesis for d in prefilter_result.dropped]
            return StrategyDecision(
                cycle_id=early_exit.cycle_id,
                decision=early_exit.decision,
                selected_strategy=early_exit.selected_strategy,
                selected_hypothesis=early_exit.selected_hypothesis,
                alternatives=early_exit.alternatives + dropped_alternatives,
                rationale=early_exit.rationale,
            )

        # Stage 2
        comparison = self.compare(viable, context)

        # Stage 3
        decision = self.select(viable, comparison, not_viable, context)
        # attach dropped alternatives
        dropped_alternatives = [d.hypothesis for d in prefilter_result.dropped]
        if dropped_alternatives:
            decision = StrategyDecision(
                **{**decision.model_dump(), "alternatives": decision.alternatives + dropped_alternatives}
            )
        return decision

    # ------------------------------------------------------------------ #
    # LLM call (extracted so tests can monkeypatch _call_llm)
    # ------------------------------------------------------------------ #

    def _call_llm(
        self,
        viable: list[StrategyHypothesis],
        comparison: list[ComparisonRow],
        not_viable: list[StrategyHypothesis],
        context: HedgeContext,
    ) -> str:
        """Make the completion call and return the raw text response.

        If no client was injected and no API key is configured, raises
        ``RuntimeError`` so the caller falls back deterministically.
        """
        from backend.llm.provider import resolve_provider

        client = self._client
        if client is None:
            provider = resolve_provider()
            if provider.api_key is None:
                raise RuntimeError("no LLM API key configured")
            client = get_llm_client()

        context_block = _build_context_block(context, viable, comparison, not_viable)
        prompt = render_prompt(_MANAGER_TEMPLATE, context_block=context_block)
        model = resolve_model("fast")

        completion = client.chat.completions.create(
            model=model,
            messages=prompt.messages,
            temperature=0,
            max_tokens=512,
        )
        return completion.choices[0].message.content or ""
