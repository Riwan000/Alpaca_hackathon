"""P4-BE-10 — every prompt template renders cleanly, within its token budget.

The templates live in ``backend/agents/prompts/templates.yaml``; each carries a
``sample`` block of render kwargs so this suite stays data-driven — adding an
agent's template is a YAML edit, not a test edit.
"""

from __future__ import annotations

import re

import pytest

from backend.agents import prompts

_LEFTOVER_RE = re.compile(r"\{[a-zA-Z_]\w*\}")
_ALL = prompts.names()

# The LLM call sites that exist by the end of Phase 4. Portfolio and Options are
# deterministic (no LLM) and intentionally have no template.
_EXPECTED = {"stock", "market", "news", "manager"}


def test_registry_loads_expected_templates() -> None:
    assert _ALL, "no prompt templates loaded from templates.yaml"
    assert _EXPECTED <= set(_ALL), f"missing templates: {_EXPECTED - set(_ALL)}"


@pytest.mark.parametrize("name", _ALL)
def test_template_renders_with_its_sample_context(name: str) -> None:
    tmpl = prompts.get(name)
    assert tmpl.sample, f"{name}: templates.yaml entry needs a 'sample' block"

    rendered = prompts.render(name, **tmpl.sample)

    assert rendered.system.strip(), f"{name}: empty system prompt after render"
    assert rendered.user.strip(), f"{name}: empty user prompt after render"


@pytest.mark.parametrize("name", _ALL)
def test_no_unfilled_placeholders(name: str) -> None:
    rendered = prompts.render(name, **prompts.get(name).sample)
    for part, text in (("system", rendered.system), ("user", rendered.user)):
        leftover = _LEFTOVER_RE.search(text)
        assert leftover is None, (
            f"{name}.{part}: unfilled placeholder {leftover.group(0)!r}"
        )


@pytest.mark.parametrize("name", _ALL)
def test_rendered_prompt_is_within_token_budget(name: str) -> None:
    tmpl = prompts.get(name)
    rendered = prompts.render(name, **tmpl.sample)
    assert rendered.token_estimate <= tmpl.max_tokens, (
        f"{name}: rendered prompt ~{rendered.token_estimate} tokens "
        f"exceeds the {tmpl.max_tokens}-token budget"
    )


@pytest.mark.parametrize("name", _ALL)
def test_messages_shape(name: str) -> None:
    rendered = prompts.render(name, **prompts.get(name).sample)
    assert [m["role"] for m in rendered.messages] == ["system", "user"]
    assert rendered.messages[0]["content"] == rendered.system
    assert rendered.messages[1]["content"] == rendered.user


def test_missing_placeholder_value_raises_prompt_error() -> None:
    with pytest.raises(prompts.PromptError):
        prompts.render("manager")  # {context_block} not supplied


def test_unknown_template_raises_prompt_error() -> None:
    with pytest.raises(prompts.PromptError):
        prompts.render("no_such_agent", foo="bar")


def test_estimate_tokens_is_ceil_of_length_over_four() -> None:
    assert prompts.estimate_tokens("") == 0
    assert prompts.estimate_tokens("abcd") == 1
    assert prompts.estimate_tokens("abcde") == 2
