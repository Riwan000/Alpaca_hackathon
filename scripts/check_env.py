"""Task P1-OPS-4 — environment preflight.

Reports the required settings that an ``.env`` file (plus the process
environment) does **not** satisfy, so a half-filled ``.env`` fails loudly before
the app tries to boot.

Usage::

    python scripts/check_env.py                 # checks ./.env
    python scripts/check_env.py --env-file .env.ci
    python scripts/check_env.py --strict        # also run full Settings validation

Prints one missing key per line to stdout and exits non-zero when any are
missing; prints nothing and exits 0 when the environment is complete.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import Settings  # noqa: E402


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from ``path`` (missing file → ``{}``)."""
    try:
        from dotenv import dotenv_values

        return {k: (v or "") for k, v in dotenv_values(path).items()}
    except ModuleNotFoundError:  # pragma: no cover - dotenv is a hard dep
        values: dict[str, str] = {}
        if not path.is_file():
            return values
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip("'\"")
        return values


def required_keys() -> list[str]:
    """Env-var names for every field ``Settings`` marks required."""
    return sorted(
        name.upper()
        for name, field in Settings.model_fields.items()
        if field.is_required()
    )


def find_missing(env_file: Path, environ: dict[str, str] | None = None) -> list[str]:
    """Required keys absent or blank across the .env file and the environment."""
    import os

    environ = os.environ if environ is None else environ
    from_file = _load_env_file(env_file)
    # Case-insensitive lookup: Settings reads env vars case-insensitively.
    lower_file = {k.lower(): v for k, v in from_file.items()}
    lower_env = {k.lower(): v for k, v in environ.items()}

    missing: list[str] = []
    for key in required_keys():
        value = lower_file.get(key.lower()) or lower_env.get(key.lower())
        if value is None or not str(value).strip():
            missing.append(key)
    return missing


def _strict_errors(env_file: Path) -> list[str]:
    """Keys that fail full ``Settings`` validation (types, constraints)."""
    from pydantic import ValidationError

    try:
        Settings(_env_file=str(env_file) if env_file.is_file() else None)
    except ValidationError as exc:
        return sorted({str(err["loc"][0]).upper() for err in exc.errors() if err.get("loc")})
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="path to the .env file (default: .env)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also run full Settings validation (types and constraints)",
    )
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    missing = find_missing(env_file)
    if args.strict:
        missing = sorted(set(missing) | set(_strict_errors(env_file)))

    for key in missing:
        print(key)

    if missing:
        print(
            f"check_env: {len(missing)} required key(s) missing from {env_file}",
            file=sys.stderr,
        )
        return 1

    print(f"check_env: {env_file} satisfies every required setting", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
