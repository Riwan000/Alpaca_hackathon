"""Backend package layout tests — task P1-BE-1.

Confirms the ``backend/`` package tree exists and every top-level package
imports cleanly in a fresh interpreter (no circular imports).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PACKAGES = (
    "backend.api",
    "backend.agents",
    "backend.quant",
    "backend.integrations",
    "backend.state",
    "backend.models",
    "backend.services",
    "backend.config",
)


def test_packages_importable() -> None:
    """Every backend package imports in a clean interpreter with no circular import."""
    for pkg in _PACKAGES:
        assert (_REPO_ROOT / Path(*pkg.split("."))).is_dir(), f"missing package dir: {pkg}"
        assert (_REPO_ROOT / Path(*pkg.split("."), "__init__.py")).is_file(), (
            f"missing __init__.py: {pkg}"
        )

    stmt = "import " + ", ".join(_PACKAGES)
    result = subprocess.run(
        [sys.executable, "-c", stmt],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"import failed (exit {result.returncode}):\n{result.stderr}"
    )
