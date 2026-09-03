"""YAML-backed prompt templates for the LLM agents and the Strategy Manager.

Task ``P4-BE-10``.  The prose lives in ``templates.yaml`` next to this module so
it can be tuned without touching Python.  :func:`render` fills ``{placeholder}``
slots (``str.format`` syntax - double any literal brace as ``{{`` / ``}}``) and
raises :class:`PromptError` on a missing or left-behind placeholder.

``tests/agents/test_prompts.py`` renders every template with its ``sample`` block
and asserts the estimate stays within ``max_tokens``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "CHARS_PER_TOKEN",
    "PromptError",
    "PromptTemplate",
    "RenderedPrompt",
    "estimate_tokens",
    "get",
    "names",
    "render",
    "templates",
]

_TEMPLATES_PATH = Path(__file__).with_name("templates.yaml")

#: Rough chars-per-token ratio for English text - enough for a budget gate
#: without taking on a tokenizer dependency.
CHARS_PER_TOKEN = 4

_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_]\w*\}")
_REQUIRED_KEYS = ("system", "user")
_DEFAULT_MAX_TOKENS = 1000


class PromptError(RuntimeError):
    """A template is malformed, unknown, or a render left a placeholder unfilled."""


@dataclass(frozen=True)
class PromptTemplate:
    """One named system/user pair loaded from ``templates.yaml``."""

    name: str
    description: str
    system: str
    user: str
    model_alias: str = "fast"
    max_tokens: int = _DEFAULT_MAX_TOKENS
    sample: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedPrompt:
    """The result of :func:`render` - filled text plus a token estimate."""

    system: str
    user: str
    token_estimate: int

    @property
    def messages(self) -> list[dict[str, str]]:
        """OpenAI-style ``messages`` list for ``chat.completions.create``."""
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
        ]


def estimate_tokens(text: str) -> int:
    """Approximate token count as ``ceil(len(text) / CHARS_PER_TOKEN)``."""
    return -(-len(text) // CHARS_PER_TOKEN)


@lru_cache(maxsize=1)
def templates() -> dict[str, PromptTemplate]:
    """Parse ``templates.yaml`` once; return ``{name: PromptTemplate}``."""
    raw = yaml.safe_load(_TEMPLATES_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise PromptError("templates.yaml must be a mapping of name -> template")

    out: dict[str, PromptTemplate] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise PromptError(f"template {name!r} must be a mapping")
        missing = [k for k in _REQUIRED_KEYS if not str(spec.get(k, "")).strip()]
        if missing:
            raise PromptError(
                f"template {name!r} missing/empty key(s): {', '.join(missing)}"
            )
        out[name] = PromptTemplate(
            name=str(name),
            description=str(spec.get("description", "")),
            system=str(spec["system"]),
            user=str(spec["user"]),
            model_alias=str(spec.get("model_alias", "fast")),
            max_tokens=int(spec.get("max_tokens", _DEFAULT_MAX_TOKENS)),
            sample=dict(spec.get("sample") or {}),
        )
    return out


def names() -> list[str]:
    """Sorted list of every template name in the registry."""
    return sorted(templates())


def get(name: str) -> PromptTemplate:
    """Return the :class:`PromptTemplate` called ``name`` or raise ``PromptError``."""
    try:
        return templates()[name]
    except KeyError:
        raise PromptError(
            f"unknown prompt template {name!r}; known: {', '.join(names())}"
        ) from None


def _fill(text: str, values: dict[str, Any], where: str) -> str:
    try:
        filled = text.format_map(values)
    except KeyError as exc:
        raise PromptError(f"{where}: no value for placeholder {exc}") from None
    except (IndexError, ValueError) as exc:
        raise PromptError(f"{where}: malformed template ({exc})") from None
    leftover = _PLACEHOLDER_RE.search(filled)
    if leftover is not None:
        raise PromptError(f"{where}: unfilled placeholder {leftover.group(0)!r}")
    return filled


def render(name: str, /, **values: Any) -> RenderedPrompt:
    """Fill ``name``'s system + user templates with ``values``.

    Raises :class:`PromptError` if the template is unknown, or a ``{placeholder}``
    has no value / survives the substitution.
    """
    tmpl = get(name)
    system = _fill(tmpl.system, values, f"{name}.system")
    user = _fill(tmpl.user, values, f"{name}.user")
    return RenderedPrompt(
        system=system,
        user=user,
        token_estimate=estimate_tokens(system) + estimate_tokens(user),
    )
