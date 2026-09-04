"""Shared fixtures for the orchestrator-node tests (P6-BE-2 … P6-BE-6).

``migrated_engine`` — a scratch SQLite database migrated to head, for the nodes
that persist (``RISK_CHECK`` → ``risk_checks``, ``EXECUTION`` → ``orders`` /
``execution_failures``, ``MONITORING`` → ``monitoring_state``).
``golden_context`` / ``golden_hedge_context`` — the recorded Phase 3
``HedgeContext`` fixture, as a raw dict and as a parsed model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.models.hedge_context import HedgeContext

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_GOLDEN = _REPO_ROOT / "tests" / "fixtures" / "analyze" / "hedge_context_golden.json"


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    """A scratch SQLite database migrated to head, disposed on teardown."""
    db_url = f"sqlite:///{tmp_path / 'orch_nodes.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed:\n{proc.stdout}\n{proc.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def golden_context() -> dict[str, Any]:
    """The recorded Phase 3 ``HedgeContext`` fixture as a raw dict."""
    return json.loads(_GOLDEN.read_text("utf-8"))


@pytest.fixture
def golden_hedge_context(golden_context: dict[str, Any]) -> HedgeContext:
    """The recorded Phase 3 ``HedgeContext`` fixture, parsed."""
    return HedgeContext.model_validate(golden_context)
