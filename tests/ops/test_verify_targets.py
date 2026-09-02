"""Task P1-OPS-2 — ``make verify-phase-1`` … ``verify-phase-8``.

Each target runs its phase's pytest selection plus a frontend subset and then
echoes that phase's acceptance block. A failing test in the selection must make
the target exit non-zero; the ``|| [ $? -eq 5 ]`` guard only forgives an *empty*
selection (pytest's "no tests collected"), never a real failure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAKEFILE = _REPO_ROOT / "Makefile"
_PHASES = tuple(range(1, 9))


def _recipe(target: str) -> str:
    """The raw recipe text (tab-indented lines) for ``target``."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = re.compile(rf"^{re.escape(target)}\s*:(?!=)")
    out: list[str] = []
    collecting = False
    for line in lines:
        if header.match(line):
            collecting = True
            continue
        if collecting:
            if line.startswith("\t"):
                out.append(line[1:])
            elif line.strip() and not line.startswith("#"):
                break
    return "\n".join(out)


@pytest.mark.parametrize("phase", _PHASES)
def test_target_defined(phase: int) -> None:
    """All eight ``verify-phase-N`` targets have a recipe."""
    assert _recipe(f"verify-phase-{phase}"), f"verify-phase-{phase} has no recipe"


@pytest.mark.parametrize("phase", _PHASES)
def test_target_runs_pytest_selection(phase: int) -> None:
    recipe = _recipe(f"verify-phase-{phase}")
    assert "pytest" in recipe or "PYTEST" in recipe, (
        f"verify-phase-{phase} runs no pytest selection:\n{recipe}"
    )


@pytest.mark.parametrize("phase", _PHASES)
def test_failure_is_not_swallowed(phase: int) -> None:
    """The recipe never forces success (no ``|| true`` / ``; true`` / ``-`` prefix)."""
    recipe = _recipe(f"verify-phase-{phase}")
    pytest_lines = [ln for ln in recipe.splitlines() if "PYTEST" in ln or "pytest" in ln]
    assert pytest_lines, f"verify-phase-{phase}: no pytest line found"
    for ln in pytest_lines:
        assert "|| true" not in ln and "; true" not in ln, (
            f"verify-phase-{phase} swallows test failures: {ln!r}"
        )
        assert not ln.lstrip().startswith("-"), (
            f"verify-phase-{phase} ignores errexit with a '-' prefix: {ln!r}"
        )
        # The only tolerated escape hatch is pytest's empty-selection code 5,
        # applied via the shared $(PYTEST_OK_IF_EMPTY) fragment.
        if "||" in ln and "PYTEST_OK_IF_EMPTY" not in ln:
            assert "$? -eq 5" in ln or "$$? -eq 5" in ln, (
                f"verify-phase-{phase}: unexpected `||` fallback: {ln!r}"
            )


def test_empty_selection_guard_is_code_5_only() -> None:
    """``$(PYTEST_OK_IF_EMPTY)`` forgives exit 5 (no tests) and nothing else."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^PYTEST_OK_IF_EMPTY\s*:?=\s*(.+)$", text, re.MULTILINE)
    assert match, "PYTEST_OK_IF_EMPTY is not defined in the Makefile"
    body = match.group(1)
    assert "-eq 5" in body and "||" in body, body


@pytest.mark.parametrize("phase", _PHASES)
def test_target_echoes_acceptance_block(phase: int) -> None:
    """Each target prints its phase-acceptance checklist from the plan."""
    recipe = _recipe(f"verify-phase-{phase}")
    assert "show-accept" in recipe or "phased-implementation-plan.md" in recipe, (
        f"verify-phase-{phase} does not echo its acceptance block:\n{recipe}"
    )


def test_frontend_subset_is_guarded() -> None:
    """The frontend slice runs only when the app is scaffolded (no hard failure)."""
    for phase in _PHASES:
        recipe = _recipe(f"verify-phase-{phase}")
        assert "run-fe" in recipe or "frontend/package.json" in recipe, (
            f"verify-phase-{phase} has no guarded frontend step:\n{recipe}"
        )


# --------------------------------------------------------------------------- #
# Behavioural check: a target's selection that contains a failing test must make
# the target exit non-zero. Proven against the same recipe shape the Makefile
# uses (pytest selection + the code-5 guard).
# --------------------------------------------------------------------------- #


def _guarded_result(selection: Path, cwd: Path) -> int:
    """Apply the Makefile guard ``pytest ... || [ $? -eq 5 ]`` in Python.

    Returns the exit code the make recipe line would produce: 0 when pytest
    passes (0) or collected nothing (5), otherwise pytest's own code.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(selection)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return 0 if proc.returncode in (0, 5) else proc.returncode


def test_guard_forgives_empty_but_not_failure(tmp_path: Path) -> None:
    failing = tmp_path / "test_boom.py"
    failing.write_text("def test_boom():\n    assert False\n", encoding="utf-8")
    passing = tmp_path / "test_ok.py"
    passing.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()

    assert _guarded_result(failing, tmp_path) != 0, "a failing test must abort the target"
    assert _guarded_result(passing, tmp_path) == 0, "a passing selection must succeed"
    assert _guarded_result(empty, tmp_path) == 0, "an empty selection must be forgiven"


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_real_target_aborts_on_failure(tmp_path: Path) -> None:
    """Run the real ``verify-phase-2`` with a planted failing quant test."""
    planted = _REPO_ROOT / "tests" / "quant" / "test_ops_probe_delete_me.py"
    planted.write_text(
        textwrap.dedent(
            """\
            import pytest

            @pytest.mark.parametrize("x", [1])
            def test_planted_failure(x):
                assert x == 2
            """
        ),
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            ["make", "verify-phase-2"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        planted.unlink(missing_ok=True)
    assert proc.returncode != 0, "verify-phase-2 should fail when a quant test fails"
    combined = proc.stdout + proc.stderr
    assert "test_planted_failure" in combined or "test_ops_probe_delete_me" in combined, (
        f"the failing test is not named in the output:\n{combined}"
    )


if __name__ == "__main__":  # pragma: no cover - manual convenience
    sys.exit(pytest.main([__file__, "-q"]))
