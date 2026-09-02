"""Task P1-OPS-4 — ``.env.example`` stays in lock-step with ``Settings``.

Every key ``Settings`` marks *required* must appear in ``.env.example`` so a
fresh clone can fill it in, and every key in ``.env.example`` must map to a real
``Settings`` field (``extra="ignore"`` would otherwise let a typo pass silently).
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"

_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def example_keys() -> set[str]:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    return {
        m.group(1)
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        for m in [_ASSIGNMENT.match(line)]
        if m
    }


def settings_env_names() -> set[str]:
    """Env var name for each ``Settings`` field (case-insensitive → UPPER)."""
    return {name.upper() for name in Settings.model_fields}


def required_env_names() -> set[str]:
    return {
        name.upper()
        for name, field in Settings.model_fields.items()
        if field.is_required()
    }


def test_env_example_exists_and_parses() -> None:
    assert _ENV_EXAMPLE.is_file(), ".env.example missing at repo root"
    assert example_keys(), ".env.example defines no KEY=VALUE lines"


def test_required_keys_present() -> None:
    missing = sorted(required_env_names() - example_keys())
    assert not missing, f".env.example is missing required Settings keys: {missing}"


def test_no_unknown_keys() -> None:
    """Guard against a key in .env.example that Settings would ignore."""
    unknown = sorted(example_keys() - settings_env_names())
    assert not unknown, (
        f".env.example has keys with no matching Settings field: {unknown}"
    )
