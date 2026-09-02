"""Task P1-OPS-4 — ``scripts/check_env.py`` preflight behaviour."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_env import find_missing, main, required_keys

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_env.py"


def _env_without_db() -> dict[str, str]:
    """A copy of the process environment with the DB keys stripped."""
    drop = {"DATABASE_URL", "DATABASE_URL_UNPOOLED"}
    return {k: v for k, v in os.environ.items() if k.upper() not in drop}


def test_required_keys_include_database_url() -> None:
    assert "DATABASE_URL" in required_keys()


def test_half_filled_env_lists_exactly_the_missing_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    # Everything a demo needs *except* the one required key.
    env_file.write_text(
        "LLM_PROVIDER=openrouter\nALPACA_API_KEY=abc\nHOST=0.0.0.0\n",
        encoding="utf-8",
    )
    missing = find_missing(env_file, environ={})
    assert missing == sorted(k for k in required_keys())
    assert "DATABASE_URL" in missing


def test_blank_value_counts_as_missing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=   \n", encoding="utf-8")
    assert "DATABASE_URL" in find_missing(env_file, environ={})


def test_complete_env_reports_nothing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://u:p@h/db\n", encoding="utf-8"
    )
    assert find_missing(env_file, environ={}) == []


def test_environment_can_satisfy_a_key_absent_from_the_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openrouter\n", encoding="utf-8")
    assert find_missing(env_file, environ={"DATABASE_URL": "postgresql://u:p@h/db"}) == []


def test_cli_exit_code_and_output(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openrouter\n", encoding="utf-8")
    scrubbed = _env_without_db()

    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--env-file", str(env_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed,
    )
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["DATABASE_URL"]

    env_file.write_text("DATABASE_URL=postgresql://u:p@h/db\n", encoding="utf-8")
    proc_ok = subprocess.run(
        [sys.executable, str(_SCRIPT), "--env-file", str(env_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed,
    )
    assert proc_ok.returncode == 0
    assert proc_ok.stdout.strip() == ""


def test_main_callable_in_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openrouter\n", encoding="utf-8")
    code = main(["--env-file", str(env_file)])
    assert code == 1
    assert "DATABASE_URL" in capsys.readouterr().out
