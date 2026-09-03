"""Golden contract test for the analysis chain — task P3-BE-13 (BRD §14, §31).

A recorded ``AnalysisInputs`` fixture + the stubbed LLM (``mock_llm``) must drive
:func:`~backend.agents.assembler.assemble_hedge_context` to a ``HedgeContext``
that matches ``tests/fixtures/analyze/hedge_context_golden.json`` — numbers
within a small tolerance, everything else exactly, ``degraded_sections`` empty.

The chain is otherwise time-sensitive (the Options agent filters on days-to-expiry
against wall-clock "today"), so the golden run pins the Options agent's clock to
``_FIXED_NOW`` — the same instant the fixture's option expiries are dated from.

Regenerate the golden after an intended change::

    WRITE_GOLDEN=1 python -m pytest tests/agents/test_analyze_golden.py -q

and review the diff before committing.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.agents.assembler import ANALYSIS_AGENT_FNS, assemble_hedge_context
from backend.agents.context_builder import AnalysisInputs
from backend.agents.options import analyze_options
from backend.models.hedge_context import HedgeContext

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analyze"
_INPUT_PATH = _FIXTURES / "portfolio_input.json"
_GOLDEN_PATH = _FIXTURES / "hedge_context_golden.json"

_FIXED_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_REL_TOL = 1e-6
_ABS_TOL = 1e-9


def _pinned_options(ctx: Any, **kwargs: Any) -> Any:
    """``analyze_options`` with its days-to-expiry clock pinned to ``_FIXED_NOW``."""
    return analyze_options(ctx, now=_FIXED_NOW, **kwargs)


def _run() -> HedgeContext:
    """Assemble the context for the recorded fixture.

    Call it only under the ``mock_llm`` fixture: the LLM-backed agents are given
    no explicit client, so they resolve the patched offline stub and every
    section falls back to its deterministic path.
    """
    inputs = AnalysisInputs.model_validate(json.loads(_INPUT_PATH.read_text("utf-8")))
    return assemble_hedge_context(
        inputs,
        agent_fns={**ANALYSIS_AGENT_FNS, "options": _pinned_options},
    )


def _diff(path: str, got: Any, want: Any) -> list[str]:
    """Return human-readable mismatch descriptions between ``got`` and ``want``."""
    if isinstance(want, bool) or isinstance(got, bool):
        return [] if got is want else [f"{path}: {got!r} != {want!r}"]
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        if math.isclose(got, want, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
            return []
        return [f"{path}: {got!r} != {want!r} (outside tolerance)"]
    if isinstance(want, dict) and isinstance(got, dict):
        out: list[str] = []
        for key in sorted(set(want) | set(got)):
            if key not in got:
                out.append(f"{path}.{key}: missing (want {want[key]!r})")
            elif key not in want:
                out.append(f"{path}.{key}: unexpected (got {got[key]!r})")
            else:
                out += _diff(f"{path}.{key}", got[key], want[key])
        return out
    if isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            return [f"{path}: length {len(got)} != {len(want)}"]
        out = []
        for i, (g, w) in enumerate(zip(got, want)):
            out += _diff(f"{path}[{i}]", g, w)
        return out
    return [] if got == want else [f"{path}: {got!r} != {want!r}"]


def test_recorded_portfolio_matches_the_golden_hedge_context(mock_llm) -> None:
    ctx = _run()
    got = ctx.model_dump(mode="json")

    if os.environ.get("WRITE_GOLDEN"):
        _GOLDEN_PATH.write_text(
            json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(f"golden rewritten: {_GOLDEN_PATH}")

    assert _GOLDEN_PATH.exists(), "run with WRITE_GOLDEN=1 to create the golden file"
    want = json.loads(_GOLDEN_PATH.read_text("utf-8"))

    mismatches = _diff("hedge_context", got, want)
    assert not mismatches, "HedgeContext drifted from the golden:\n" + "\n".join(mismatches)


def test_the_golden_run_is_not_degraded(mock_llm) -> None:
    assert _run().degraded_sections == []


def test_golden_is_stable_across_two_runs(mock_llm) -> None:
    assert _run().model_dump(mode="json") == _run().model_dump(mode="json")
