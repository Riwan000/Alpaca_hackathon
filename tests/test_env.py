"""Environment / dependency manifest tests — task P1-BE-2.

Confirms the core backend third-party stack is installed and importable at the
expected major versions, so a fresh ``pip install -r requirements.txt`` yields a
working interpreter before any application code runs.
"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata

import pytest

# (import name, distribution name, expected major version or None to skip the check)
_CORE_DEPS = (
    ("fastapi", "fastapi", 0),
    ("pydantic", "pydantic", 2),
    ("alpaca", "alpaca-py", 0),
    ("langgraph", "langgraph", 1),
    ("httpx", "httpx", 0),
    ("uvicorn", "uvicorn", 0),
    ("asyncpg", "asyncpg", 0),
    ("openai", "openai", None),
)


def _major(version: str) -> int:
    return int(version.split(".", 1)[0])


@pytest.mark.parametrize(("module_name", "dist_name", "expected_major"), _CORE_DEPS)
def test_core_imports(module_name: str, dist_name: str, expected_major: int | None) -> None:
    """Every core dependency imports and reports the pinned major version."""
    module = importlib.import_module(module_name)
    assert module is not None

    installed = metadata.version(dist_name)
    if expected_major is not None:
        assert _major(installed) == expected_major, (
            f"{dist_name} major version {installed!r} != expected {expected_major}"
        )


def test_pydantic_is_v2() -> None:
    """Pydantic resolves to the v2 line (v1 API is incompatible)."""
    import pydantic

    assert pydantic.VERSION.startswith("2."), pydantic.VERSION


def test_langgraph_graph_api_present() -> None:
    """langgraph exposes the StateGraph builder used by the orchestrator."""
    from langgraph.graph import StateGraph

    assert StateGraph is not None


def test_test_tooling_present() -> None:
    """pytest-cov is installed so ``pytest --cov`` works in CI."""
    assert metadata.version("pytest-cov")
