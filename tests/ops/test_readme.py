"""Task P1-OPS-5 — the README "Run it yourself" section is present and runnable.

The CI ``docs-commands`` job executes the README's runnable blocks; these checks
guard the structure locally so that job cannot silently lose its input.
"""

from __future__ import annotations

from pathlib import Path

from scripts.run_doc_commands import build_script, extract_blocks

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README = _REPO_ROOT / "README.md"


def _text() -> str:
    return _README.read_text(encoding="utf-8")


def test_readme_exists() -> None:
    assert _README.is_file(), "root README.md is missing"


def test_run_it_yourself_section_present() -> None:
    text = _text().lower()
    assert "## run it yourself" in text


def test_explains_test_and_confirm_lines() -> None:
    text = _text()
    assert "`Test:`" in text and "`Confirm:`" in text, (
        "README does not explain how to read a task's Test: / Confirm: lines"
    )


def test_has_local_bringup_commands() -> None:
    text = _text()
    for needle in ("alembic -c backend/alembic.ini upgrade head", "uvicorn backend.api.app:app", "/health"):
        assert needle in text, f"README is missing the bring-up step: {needle!r}"


def test_has_runnable_ci_block() -> None:
    blocks = extract_blocks(_text())
    assert blocks, "README has no ```bash ci``` block for the docs-commands job"
    script = build_script(blocks)
    assert "pip install -r requirements.txt" in script
    assert "pytest" in script


def test_ci_block_stays_offline() -> None:
    """The CI-executed block must not depend on a live DB or credentials."""
    script = build_script(extract_blocks(_text()))
    for forbidden in ("backend.seed", "alembic", "curl ", "-m smoke", "make dev"):
        assert forbidden not in script, (
            f"the ```bash ci``` block references {forbidden!r} — it must run without "
            "a database or network"
        )
