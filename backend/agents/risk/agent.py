"""Risk Agent — tasks **P5-BE-8** / **P5-BE-9** (BRD §19–20).

The Risk Agent is the last gate before execution. It runs *after* the
deterministic risk engine (:func:`backend.agents.risk.aggregate.aggregate_risk`)
and adds the qualitative judgement the pure checks cannot make — but it works
inside two hard rails:

* **it cannot override a deterministic failure.** When any hard check fails the
  verdict is ``REJECT``, full stop — the LLM is not even consulted, so an
  "approve" hallucination can never clear a plan the engine already blocked.
* **it cannot invent or swap a strategy.** ``approved_hypothesis`` is always the
  hypothesis that came in; any ``strategy`` / ``strategy_type`` key in the LLM
  response, or a modification that targets the strategy family, is dropped.

On a deterministically-clean plan the LLM returns one of ``APPROVE`` /
``MODIFY`` / ``REJECT``; any LLM failure (no key, timeout, unparsable output)
falls back to ``APPROVE`` — the deterministic layer has already cleared every
hard limit. The result is a :class:`~backend.models.risk.RiskDecision`, and when
a :class:`~backend.db.risk_checks_repo.RiskCheckRepository` is supplied it is
persisted as exactly one ``risk_checks`` row (P5-BE-9).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from backend.agents.prompts import render as render_prompt
from backend.agents.risk.aggregate import (
    DEFAULT_CHECKS,
    AggregateRiskResult,
    DeterministicCheck,
    aggregate_risk,
)
from backend.agents.risk.engine import RiskEngineLimits
from backend.llm.provider import get_llm_client, resolve_model
from backend.models.enums import RiskVerdict
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskDecision, RiskModification
from backend.models.strategy import StrategyHypothesis

if TYPE_CHECKING:  # avoid importing the DB layer unless persistence is used
    from collections.abc import Sequence

    from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository

__all__ = ["RiskAgent", "persist_risk_decision"]

logger = logging.getLogger(__name__)

_RISK_TEMPLATE = "risk"
_LLM_VERDICTS = ("APPROVE", "MODIFY", "REJECT")

#: Fields a MODIFY adjustment may never touch — the strategy family is fixed by
#: the Strategy Manager, not the Risk Agent.
_STRATEGY_FIELDS = frozenset({"strategy", "strategy_type", "selected_strategy", "family"})


# --------------------------------------------------------------------------- #
# LLM response parsing
# --------------------------------------------------------------------------- #


def _parse_llm_response(text: str) -> dict[str, Any]:
    """Parse the LLM text into a verdict dict; raise ``ValueError`` on failure."""
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.startswith("```")
        ).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    verdict = data.get("verdict")
    if verdict not in _LLM_VERDICTS:
        raise ValueError(f"unknown risk verdict {verdict!r}; expected one of {_LLM_VERDICTS}")
    return data


def _coerce_scalar(value: Any) -> float | str | None:
    """Coerce an LLM-supplied modification value onto ``float | str | None``."""
    if value is None or isinstance(value, (int, float, str)):
        return value
    return str(value)


def _parse_modifications(raw: Any) -> list[RiskModification]:
    """Build the concrete adjustments from the LLM ``modifications`` list.

    Entries missing a ``field`` or ``reason`` are skipped; any entry that would
    change the strategy family is dropped (the Risk Agent cannot swap strategy).
    """
    if not isinstance(raw, list):
        return []
    out: list[RiskModification] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not field or not reason or field.lower() in _STRATEGY_FIELDS:
            continue
        out.append(
            RiskModification(
                field=field,
                from_value=_coerce_scalar(item.get("from_value")),
                to_value=_coerce_scalar(item.get("to_value")),
                reason=reason,
            )
        )
    return out


def _clean_str_list(raw: Any) -> list[str]:
    """Non-empty, stripped strings from an LLM list field (``[]`` on anything else)."""
    if not isinstance(raw, list):
        return []
    return [s for s in (str(item).strip() for item in raw) if s]


def _merge_warnings(deterministic: list[str], llm: list[str]) -> list[str]:
    """Deterministic soft-warnings first, then any LLM cautions, de-duplicated."""
    out: list[str] = []
    for item in (*deterministic, *llm):
        if item and item not in out:
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# prompt context block
# --------------------------------------------------------------------------- #


def _build_context_block(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    aggregate: AggregateRiskResult,
) -> str:
    """Render the ``{context_block}`` the ``risk`` template wraps."""
    parts: list[str] = ["=== Proposed Hedge ==="]
    parts.append(
        f"Strategy: {hypothesis.strategy.value} | action: {hypothesis.action.value} "
        f"| cost: ${hypothesis.cost:,.0f}"
    )
    if hypothesis.legs:
        parts.append("Legs:")
        for leg in hypothesis.legs:
            parts.append(
                f"  {leg.side.value} {leg.quantity} {leg.underlying} {leg.right.value} "
                f"{leg.strike:g} exp {leg.expiration.isoformat()}"
            )
    metrics = hypothesis.hedge_metrics
    if metrics.hedge_ratio is not None or metrics.downside_protection_pct is not None:
        parts.append(
            f"Hedge ratio: {metrics.hedge_ratio or 0:.2f} | "
            f"downside protection: {(metrics.downside_protection_pct or 0):.1%}"
        )
    parts.append("")

    portfolio = context.portfolio_state
    parts.append("=== Portfolio Context ===")
    parts.append(f"Total value: ${portfolio.total_value:,.0f}")
    parts.append(
        f"Drawdown tolerance: {context.objective.drawdown_tolerance_pct:.1%} | "
        f"hedge budget (max): {context.objective.max_hedge_budget_pct:.1%}"
    )
    if context.market_state and context.market_state.regime:
        parts.append(f"Market regime: {context.market_state.regime}")
    if context.degraded_sections:
        parts.append(f"⚠ Degraded analysis sections: {', '.join(context.degraded_sections)}")
    parts.append("")

    parts.append(f"=== Deterministic Risk Checklist ({aggregate.summary()}) ===")
    for check in aggregate.checks:
        flag = "PASS" if check.passed else "FAIL"
        parts.append(f"  [{flag}] {check.name}: {check.detail or '(no detail)'}")

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# RiskAgent
# --------------------------------------------------------------------------- #


class RiskAgent:
    """The non-negotiable safety gate (BRD §20).

    ::

        agent    = RiskAgent()
        decision = agent.review(approved_hypothesis, context, repo=risk_repo)
    """

    def __init__(self, *, client: OpenAI | None = None) -> None:
        self._client = client

    def review(
        self,
        hypothesis: StrategyHypothesis,
        context: HedgeContext,
        *,
        client: OpenAI | None = None,
        limits: RiskEngineLimits | None = None,
        checks: "Sequence[DeterministicCheck]" = DEFAULT_CHECKS,
        repo: "RiskCheckRepository | None" = None,
    ) -> RiskDecision:
        """Run the gate and return the :class:`RiskDecision`.

        When ``repo`` is supplied the decision is also written as one
        ``risk_checks`` row (P5-BE-9) before it is returned.
        """
        if client is not None:
            self._client = client

        aggregate = aggregate_risk(hypothesis, context, checks=checks, limits=limits)

        if not aggregate.passed:
            # Rail 1: a deterministic failure is final — the LLM is not consulted.
            decision = self._forced_reject(hypothesis, aggregate)
        else:
            decision = self._llm_review(hypothesis, context, aggregate)

        # Rail 2: the Risk Agent never changes the strategy family.
        approved = decision.approved_hypothesis
        if approved is not None and approved.strategy is not hypothesis.strategy:
            raise RuntimeError(
                "RiskAgent must not change the strategy family "
                f"({hypothesis.strategy.value} -> {approved.strategy.value})"
            )

        if repo is not None:
            persist_risk_decision(decision, repo)
        return decision

    # ------------------------------------------------------------------ #
    # deterministic REJECT
    # ------------------------------------------------------------------ #

    @staticmethod
    def _forced_reject(
        hypothesis: StrategyHypothesis, aggregate: AggregateRiskResult
    ) -> RiskDecision:
        codes = ", ".join(code.value for code in aggregate.violation_codes)
        return RiskDecision(
            cycle_id=hypothesis.cycle_id,
            verdict=RiskVerdict.REJECT,
            checks=aggregate.checks,
            violations=aggregate.violations,
            warnings=list(aggregate.warnings),
            modifications=[],
            rationale=(
                "Deterministic risk checks failed"
                + (f" ({codes})" if codes else "")
                + "; the Risk Agent cannot override a hard-limit rejection. "
                + aggregate.summary()
                + "."
            ),
            approved_hypothesis=None,
        )

    # ------------------------------------------------------------------ #
    # qualitative LLM review (deterministic checks already clean)
    # ------------------------------------------------------------------ #

    def _llm_review(
        self,
        hypothesis: StrategyHypothesis,
        context: HedgeContext,
        aggregate: AggregateRiskResult,
    ) -> RiskDecision:
        try:
            raw = self._call_llm(hypothesis, context, aggregate)
            parsed = _parse_llm_response(raw)
        except Exception as exc:  # no key / network / unparsable → deterministic APPROVE
            logger.warning(
                "RiskAgent.review: LLM path unavailable (%s); approving on deterministic clearance",
                exc,
            )
            return self._deterministic_approve(hypothesis, aggregate, note=str(exc))

        verdict = parsed["verdict"]
        rationale = str(parsed.get("rationale", "")).strip()
        warnings = _merge_warnings(
            aggregate.warnings, _clean_str_list(parsed.get("warnings"))
        )

        if verdict == "REJECT":
            violations = _clean_str_list(parsed.get("violations")) or [
                rationale or "Risk Agent rejected the plan on qualitative grounds"
            ]
            return RiskDecision(
                cycle_id=hypothesis.cycle_id,
                verdict=RiskVerdict.REJECT,
                checks=aggregate.checks,
                violations=violations,
                warnings=warnings,
                modifications=[],
                rationale=rationale or "; ".join(violations),
                approved_hypothesis=None,
            )

        if verdict == "MODIFY":
            modifications = _parse_modifications(parsed.get("modifications"))
            if not modifications:
                logger.warning(
                    "RiskAgent.review: MODIFY verdict carried no usable modification; approving instead"
                )
                return self._deterministic_approve(
                    hypothesis, aggregate, note="LLM MODIFY without a concrete modification"
                )
            return RiskDecision(
                cycle_id=hypothesis.cycle_id,
                verdict=RiskVerdict.MODIFY,
                checks=aggregate.checks,
                violations=[],
                warnings=warnings,
                modifications=modifications,
                rationale=rationale
                or "Risk Agent proposed adjustments before execution.",
                # the (unmodified) hypothesis is what clears; the Execution Agent
                # (P5-BE-10) applies the modifications when it builds the plan.
                approved_hypothesis=hypothesis,
            )

        # APPROVE
        return RiskDecision(
            cycle_id=hypothesis.cycle_id,
            verdict=RiskVerdict.APPROVE,
            checks=aggregate.checks,
            violations=[],
            warnings=warnings,
            modifications=[],
            rationale=rationale
            or f"No qualitative risk beyond the checklist; {aggregate.summary()}.",
            approved_hypothesis=hypothesis,
        )

    @staticmethod
    def _deterministic_approve(
        hypothesis: StrategyHypothesis,
        aggregate: AggregateRiskResult,
        *,
        note: str = "",
    ) -> RiskDecision:
        rationale = f"All deterministic risk checks passed; {aggregate.summary()}."
        if note:
            rationale += f" (LLM risk review unavailable: {note})"
        return RiskDecision(
            cycle_id=hypothesis.cycle_id,
            verdict=RiskVerdict.APPROVE,
            checks=aggregate.checks,
            violations=[],
            warnings=list(aggregate.warnings),
            modifications=[],
            rationale=rationale,
            approved_hypothesis=hypothesis,
        )

    # ------------------------------------------------------------------ #
    # LLM call (extracted so tests can monkeypatch _call_llm)
    # ------------------------------------------------------------------ #

    def _call_llm(
        self,
        hypothesis: StrategyHypothesis,
        context: HedgeContext,
        aggregate: AggregateRiskResult,
    ) -> str:
        """Make the completion call and return the raw text response."""
        from backend.llm.provider import resolve_provider

        client = self._client
        if client is None:
            provider = resolve_provider()
            if provider.api_key is None:
                raise RuntimeError("no LLM API key configured")
            client = get_llm_client()

        context_block = _build_context_block(hypothesis, context, aggregate)
        prompt = render_prompt(_RISK_TEMPLATE, context_block=context_block)
        completion = client.chat.completions.create(
            model=resolve_model("fast"),
            messages=prompt.messages,
            temperature=0,
            max_tokens=512,
        )
        return completion.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# persistence (P5-BE-9)
# --------------------------------------------------------------------------- #


def persist_risk_decision(
    decision: RiskDecision, repo: "RiskCheckRepository"
) -> "RiskCheckRecord":
    """Write ``decision`` as exactly one ``risk_checks`` row.

    The full deterministic ``checks`` list and the ``violations`` / ``warnings``
    / ``modifications`` behind the verdict ride along as JSON. Empty lists are
    stored as ``NULL`` so the repository's verdict invariants (REJECT → ≥1
    violation, MODIFY → ≥1 modification, APPROVE → no violation) line up with
    :class:`RiskDecision`'s own.
    """
    from backend.db.risk_checks_repo import RiskCheckRecord

    record = RiskCheckRecord(
        cycle_id=decision.cycle_id,
        verdict=decision.verdict.value,
        checks=[check.model_dump(mode="json") for check in decision.checks] or None,
        violations=list(decision.violations) or None,
        warnings=list(decision.warnings) or None,
        modifications=[mod.model_dump(mode="json") for mod in decision.modifications]
        or None,
    )
    return repo.create(record)
