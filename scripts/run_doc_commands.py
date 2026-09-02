"""Task P1-OPS-5 — execute the runnable command blocks in a Markdown doc.

The CI ``docs-commands`` job runs this against ``README.md`` so the "Run it
yourself" instructions can never rot: if a documented command stops working, CI
goes red.

A fenced block is *runnable* when its info string names a shell language and
carries a ``ci`` token::

    ```bash ci
    python -m pip install -r requirements.txt
    ```

All runnable blocks are concatenated (in document order) into one script and
executed with ``bash -euo pipefail``.

Usage::

    python scripts/run_doc_commands.py README.md          # run them
    python scripts/run_doc_commands.py README.md --list    # just print them
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_FENCE = re.compile(
    r"^```(?P<info>[^\n`]*)\n(?P<body>.*?)^```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_SHELL_LANGS = {"bash", "sh", "shell", "console"}
_RUN_TOKEN = "ci"


def extract_blocks(markdown: str) -> list[str]:
    """Return the bodies of every runnable (shell + ``ci``) fenced block."""
    blocks: list[str] = []
    for match in _FENCE.finditer(markdown):
        tokens = match.group("info").strip().split()
        if not tokens:
            continue
        lang, *rest = tokens
        if lang.lower() in _SHELL_LANGS and _RUN_TOKEN in rest:
            blocks.append(match.group("body").rstrip() + "\n")
    return blocks


def build_script(blocks: list[str]) -> str:
    return "set -euo pipefail\n\n" + "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("doc", help="path to the Markdown file")
    parser.add_argument("--list", action="store_true", help="print the blocks and exit")
    args = parser.parse_args(argv)

    doc = Path(args.doc)
    if not doc.is_file():
        print(f"run_doc_commands: no such file: {doc}", file=sys.stderr)
        return 2

    blocks = extract_blocks(doc.read_text(encoding="utf-8"))
    if not blocks:
        print(
            f"run_doc_commands: {doc} has no runnable ```bash ci``` blocks",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for i, block in enumerate(blocks, 1):
            print(f"# --- block {i} " + "-" * 50)
            print(block.rstrip())
        return 0

    bash = shutil.which("bash")
    if bash is None:
        print("run_doc_commands: bash is required to execute blocks", file=sys.stderr)
        return 2

    script = build_script(blocks)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(script)
        script_path = handle.name

    try:
        proc = subprocess.run([bash, script_path], cwd=doc.resolve().parent, check=False)
        return proc.returncode
    finally:
        Path(script_path).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
