"""``LLM_PROVIDER`` abstraction — task P1-BE-5.

One OpenAI-compatible client, two interchangeable backends:

* ``openrouter``  — development / iterative testing
* ``featherless`` — judging / final evaluation

The active backend is chosen by the ``LLM_PROVIDER`` env var
(:pyattr:`backend.config.Settings.llm_provider`). :data:`MODEL_MAP` maps a
logical alias (``"default"``, ``"fast"``, ``"reasoning"``) to the concrete
model id for each backend; ``"default"`` defers to the per-provider model from
the environment so it can be overridden without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from backend.config import LlmProvider, Settings, get_settings

# alias -> {provider -> concrete model id}. "default" is resolved from settings.
MODEL_MAP: dict[str, dict[LlmProvider, str]] = {
    "fast": {
        "openrouter": "anthropic/claude-3.5-haiku",
        "featherless": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    },
    "reasoning": {
        "openrouter": "anthropic/claude-3.5-sonnet",
        "featherless": "meta-llama/Meta-Llama-3.1-70B-Instruct",
    },
}

DEFAULT_ALIAS = "default"


@dataclass(frozen=True)
class ProviderConfig:
    """Everything needed to talk to the active provider — no client yet."""

    name: LlmProvider
    base_url: str
    model: str
    api_key: str | None


def resolve_model(alias: str, settings: Settings | None = None) -> str:
    """Resolve a logical model alias to a concrete model id for the active provider."""
    cfg = settings or get_settings()
    if alias == DEFAULT_ALIAS:
        return cfg.llm_model
    try:
        return MODEL_MAP[alias][cfg.llm_provider]
    except KeyError as exc:
        known = ", ".join([DEFAULT_ALIAS, *MODEL_MAP])
        raise KeyError(f"unknown model alias {alias!r}; known aliases: {known}") from exc


def resolve_provider(
    settings: Settings | None = None, *, alias: str = DEFAULT_ALIAS
) -> ProviderConfig:
    """Return the resolved :class:`ProviderConfig` for the active provider."""
    cfg = settings or get_settings()
    key = cfg.llm_api_key
    # An empty / whitespace-only env var (``OPENROUTER_API_KEY=``) counts as
    # "not configured" so callers skip live calls instead of 401-ing.
    raw_key = key.get_secret_value().strip() if key is not None else None
    return ProviderConfig(
        name=cfg.llm_provider,
        base_url=cfg.llm_base_url,
        model=resolve_model(alias, cfg),
        api_key=raw_key or None,
    )


def get_llm_client(
    settings: Settings | None = None, *, alias: str = DEFAULT_ALIAS
) -> OpenAI:
    """Return an OpenAI-compatible client pointed at the active provider.

    ``api_key`` is required by the SDK constructor; when no key is configured a
    placeholder is passed so client creation still succeeds (any real request
    will 401). Callers that need a live call should check
    ``resolve_provider().api_key`` first.
    """
    cfg = resolve_provider(settings, alias=alias)
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "missing")
