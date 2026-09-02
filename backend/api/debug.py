"""Debug routes — non-production introspection helpers.

``GET /debug/llm`` echoes the resolved LLM provider, model and base URL so the
``LLM_PROVIDER`` toggle (task P1-BE-5) can be confirmed without reading logs.
The API key is never included — only whether one is configured.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import Settings
from backend.llm import resolve_provider

router = APIRouter(prefix="/debug", tags=["debug"])


class LlmDebugResponse(BaseModel):
    provider: str
    model: str
    base_url: str
    api_key_configured: bool


@router.get("/llm", response_model=LlmDebugResponse)
def llm_debug() -> LlmDebugResponse:
    """Echo the resolved LLM provider/model/base URL.

    Stays up even when unrelated required settings (e.g. ``DATABASE_URL``) are
    missing: the LLM fields all have defaults, so we fall back to a
    validation-free ``Settings`` that reads only the LLM env vars.
    """
    try:
        cfg = resolve_provider()
    except Exception:
        cfg = resolve_provider(Settings.model_construct())
    return LlmDebugResponse(
        provider=cfg.name,
        model=cfg.model,
        base_url=cfg.base_url,
        api_key_configured=cfg.api_key is not None,
    )
