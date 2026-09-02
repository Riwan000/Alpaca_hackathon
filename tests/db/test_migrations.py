"""Migration tooling smoke test — task P1-DB-2.

``alembic upgrade head`` then ``alembic downgrade base`` must both exit 0 on a
throwaway database, and the upgrade must create Alembic's ``alembic_version``
bookkeeping table.

Scratch DB, in order of preference:

* ``$TEST_DATABASE_URL`` — a real Postgres (what CI's ``db-fresh`` job wires);
* otherwise a local throwaway SQLite file, so the test stays hermetic and
  offline.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from backend.db import OVERRIDE_ENV_VAR, normalize_driver

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"
_VERSION_TABLE = "alembic_version"


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def test_up_then_down(tmp_path: Path) -> None:
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        tables = inspect(engine).get_table_names()
    finally:
        engine.dispose()
    assert _VERSION_TABLE in tables, (
        f"upgrade did not create {_VERSION_TABLE!r}; found {sorted(tables)}"
    )

    down = _run_alembic("downgrade", "base", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade base` failed:\n{down.stdout}\n{down.stderr}"
    )
