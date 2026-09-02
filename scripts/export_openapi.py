"""Emit the backend OpenAPI schema as a checked-in artifact — task P1-BE-16.

The frontend builds its API client from ``openapi.json`` at the repo root. This
script (re)generates that file from the live FastAPI app; ``make openapi`` runs
it and CI fails if the result differs from what is committed
(:mod:`tests.api.test_openapi`).

Usage::

    python -m scripts.export_openapi           # rewrite openapi.json
    python -m scripts.export_openapi --check    # exit 1 if it would change
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OPENAPI_PATH = _REPO_ROOT / "openapi.json"


def build_spec() -> dict[str, Any]:
    """Return the OpenAPI document for the fully-wired application."""
    from backend.api import create_app

    return create_app().openapi()


def render(spec: dict[str, Any]) -> str:
    """Serialize ``spec`` deterministically (stable key order, trailing newline)."""
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(path: Path = OPENAPI_PATH) -> str:
    """Render the current spec to ``path`` and return what was written."""
    text = render(build_spec())
    path.write_text(text, encoding="utf-8")
    return text


def _check(path: Path = OPENAPI_PATH) -> int:
    want = render(build_spec())
    have = path.read_text(encoding="utf-8") if path.exists() else ""
    if want == have:
        print(f"{path.name} is up to date")
        return 0
    print(f"{path.name} is stale — run `make openapi`", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if openapi.json is out of date",
    )
    args = parser.parse_args(argv)

    if args.check:
        return _check()
    write()
    print(f"wrote {OPENAPI_PATH.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
