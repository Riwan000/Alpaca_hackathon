"""LLM smoke test — task P1-BE-6.

One cheap real completion against the configured provider. Marked ``smoke`` so
it is deselected by default (``pytest`` collects but does not run it without
``-m smoke``); it also self-skips when the active provider has no API key.

Run:  pytest -m smoke tests/llm
"""

from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.llm import get_llm_client, resolve_provider

pytestmark = pytest.mark.smoke


def test_llm_completion_returns_text() -> None:
    """A minimal completion against the live provider returns non-empty text."""
    settings = get_settings()
    cfg = resolve_provider(settings)
    if cfg.api_key is None:
        pytest.skip(f"no API key configured for provider {cfg.name!r}")

    client = get_llm_client(settings)
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "user", "content": "Reply with the single word: pong"}],
        max_tokens=8,
        temperature=0,
    )

    text = (completion.choices[0].message.content or "").strip()
    assert text, "provider returned an empty completion"
