"""Task P1-OPS-1 — the ``Makefile`` covers every target the plan references.

The plan (``docs/phased-implementation-plan.md``) is the spec: any ``make
<target>`` it names, plus the explicit list in the P1-OPS-1 task line, must be a
real target in the ``Makefile``. ``make test`` must also resolve cleanly on a
fresh checkout (checked with ``make -n`` where ``make`` is installed).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAKEFILE = _REPO_ROOT / "Makefile"
_PLAN = _REPO_ROOT / "docs" / "phased-implementation-plan.md"

# The P1-OPS-1 task line names these explicitly.
_REQUIRED_BY_TASK = {
    "dev",
    "test",
    "smoke",
    "cov",
    "migrate",
    "seed",
    "db-reset",
    "db-fresh",
    "openapi",
    "demo-restore",
}

_TARGET_DEF = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]*)\s*:(?!=)", re.MULTILINE)
_MAKE_REF = re.compile(r"\bmake\s+([a-z][a-z0-9-]*)")


def _makefile_text() -> str:
    return _MAKEFILE.read_text(encoding="utf-8")


def defined_targets() -> set[str]:
    """Every target with a rule in the Makefile."""
    text = _makefile_text()
    targets: set[str] = set(_TARGET_DEF.findall(text))
    # Also honour names declared .PHONY even if their rule is generated.
    for line in text.splitlines():
        if line.strip().startswith(".PHONY:"):
            targets.update(line.split(":", 1)[1].split())
    return targets


def referenced_targets() -> set[str]:
    """Every ``make <target>`` the plan document mentions.

    The plan writes the phase-verify family as ``make verify-phase-N``; that
    placeholder stands for all eight. ``make`` also appears in prose ("make the
    behavior visible") — keep only tokens that look like a target (hyphenated,
    or one of the names the P1-OPS-1 task line spells out).
    """
    plan = _PLAN.read_text(encoding="utf-8")
    refs: set[str] = set()
    for raw in _MAKE_REF.findall(plan):
        name = raw.rstrip("-")
        if name in {"verify-phase", "verify-phase-n"}:
            refs.update(f"verify-phase-{i}" for i in range(1, 9))
        elif "-" in name or name in _REQUIRED_BY_TASK:
            refs.add(name)
    return refs


def test_makefile_exists() -> None:
    assert _MAKEFILE.is_file(), "Makefile missing at repo root"


def test_task_required_targets_present() -> None:
    """Every target named in the P1-OPS-1 task line exists."""
    missing = sorted(_REQUIRED_BY_TASK - defined_targets())
    assert not missing, f"Makefile is missing P1-OPS-1 targets: {missing}"


def test_every_plan_referenced_target_exists() -> None:
    """Every ``make <target>`` anywhere in the plan resolves to a real rule."""
    missing = sorted(referenced_targets() - defined_targets())
    assert not missing, (
        "the plan references make targets that the Makefile does not define: "
        f"{missing}"
    )


def test_test_target_runs_pytest() -> None:
    """``make test`` drives the backend suite (pytest), not something else."""
    text = _makefile_text()
    assert re.search(r"^PYTEST\s*:?=\s*.*pytest", text, re.MULTILINE), (
        "PYTEST is not defined as a pytest invocation"
    )
    recipe = _target_recipe(text, "test")
    assert any("pytest" in line or "$(PYTEST)" in line for line in recipe), (
        f"`test` target does not invoke pytest; recipe was: {recipe}"
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_dry_run_resolves() -> None:
    """``make -n test`` / ``-n dev`` expand without a Makefile error."""
    for target in ("test", "dev", "db-fresh", "demo-restore"):
        proc = subprocess.run(
            ["make", "-n", target],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, (
            f"`make -n {target}` failed:\n{proc.stdout}\n{proc.stderr}"
        )


def _target_recipe(text: str, target: str) -> list[str]:
    """Return the recipe lines (tab-indented) for ``target``."""
    lines = text.splitlines()
    out: list[str] = []
    collecting = False
    header = re.compile(rf"^{re.escape(target)}\s*:(?!=)")
    for line in lines:
        if header.match(line):
            collecting = True
            continue
        if collecting:
            if line.startswith("\t"):
                out.append(line.strip())
            elif line.strip() == "" or line.startswith("#"):
                continue
            else:
                break
    return out
