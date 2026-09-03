"""Shared plumbing for the Phase 3 analysis agents (P3-BE-5 … P3-BE-9).

Each analysis agent is a small callable that turns one
:class:`~backend.agents.context_builder.AgentContextSlice` into its slice of the
:class:`~backend.models.hedge_context.HedgeContext`. Two rules hold across all
five (BRD §10, §13):

* the **numbers** come from :mod:`backend.quant` — deterministic and unit-tested,
  never invented by the model;
* the **LLM** only supplies prose / labels (a risk note, a regime word, a
  sentiment score). Its output is always schema-checked with a deterministic
  fallback, so a bad completion degrades a section rather than crashing the pass.

:func:`complete_json` is the single place that talks to the provider; the
deterministic agents (Portfolio, Options) never call it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

import backend.llm as _llm

logger = logging.getLogger(__name__)

__all__ = ["AgentError", "complete_json", "parse_json_object"]

#: Logical model alias for the short "narrative" call an LLM-backed agent makes.
NARRATIVE_ALIAS = "fast"
_MAX_TOKENS = 900
_TEMPERATURE = 0.0
_ERROR_PREVIEW_CHARS = 200


class AgentError(RuntimeError):
    """An analysis agent could not produce its section.

    The HedgeContext assembler (P3-BE-10) catches this, records the section name
    in ``degraded_sections`` and carries on.
    """


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse an LLM response that should carry a single JSON object.

    Tolerates a ```` ```json ```` fence and leading / trailing prose by taking
    the span between the first ``{`` and the last ``}``.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            if cleaned.lstrip()[:4].lower() == "json":
                cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AgentError(
            f"no JSON object in LLM response: {text[:_ERROR_PREVIEW_CHARS]!r}"
        )
    try:
        obj = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AgentError(f"invalid JSON in LLM response: {exc}") from exc
    if not isinstance(obj, dict):
        raise AgentError("LLM response JSON was not an object")
    return obj


def complete_json(
    system: str,
    user: str,
    *,
    client: OpenAI | None = None,
    alias: str = NARRATIVE_ALIAS,
) -> dict[str, Any]:
    """Run one chat completion and return its parsed JSON object.

    Raises :class:`AgentError` on any transport error or unparseable body, so a
    caller can fall back to a deterministic result in one ``except`` clause.
    """
    try:
        model = _llm.resolve_provider(alias=alias).model
    except Exception:  # noqa: BLE001 - settings may be absent in a unit test
        model = "default"
    try:
        llm = client or _llm.get_llm_client(alias=alias)
        completion = llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades the section, never crashes the pass
        raise AgentError(f"LLM call failed: {exc}") from exc
    try:
        content = completion.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise AgentError("LLM response carried no message content") from exc
    return parse_json_object(content)
