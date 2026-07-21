#!/usr/bin/env python3
"""Inject (or verify) the `// @generated` header on compiled TS->JS output.

The header must be the first line, except when the file has a shebang
(`#!...`), in which case it must be the second line — Node/AutoJs6 entry
points need the shebang to stay on line 1 to remain executable.

Previously implemented as a shell script driving sed's "1a" (append) and
"1s/^/.../ " (substitute) commands, whose exact behavior — particularly
literal-newline handling in a substitution replacement — differs between
sed implementations (e.g. GNU sed vs BSD/macOS sed) in ways that are easy
to get subtly wrong and hard to verify without running on every platform
the script might execute on (this repo's CI runs Ubuntu/GNU sed; local dev
is macOS/BSD sed). A plain Python string/line operation has no such
platform-dependent behavior and is directly unit-testable.

Usage:
  python3 just/tools/add_generated_header.py            # inject (mutates files)
  python3 just/tools/add_generated_header.py --check    # verify only, exit 1 if any missing
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HEADER = "// @generated"
SCAN_DIRS = ("device/autojs6", "tests/js", "just/tools", "docs/research")
EXCLUDE_DIR_NAMES = frozenset({"node_modules", ".git"})


def find_js_files(repo_root: Path) -> list[Path]:
    """All *.js files under SCAN_DIRS, deterministically ordered, excluding node_modules/.git."""
    out: list[Path] = []
    for rel_dir in SCAN_DIRS:
        root = repo_root / rel_dir
        if not root.is_dir():
            continue
        for path in root.rglob("*.js"):
            if EXCLUDE_DIR_NAMES.intersection(path.relative_to(root).parts[:-1]):
                continue
            out.append(path)
    return sorted(out)


def header_line_index(text: str) -> int:
    """Index into `splitlines()` where the header belongs: 0, or 1 after a shebang."""
    first_newline = text.find("\n")
    first_line = text if first_newline == -1 else text[:first_newline]
    return 1 if first_line.startswith("#!") else 0


def has_header(text: str) -> bool:
    lines = text.splitlines()
    idx = header_line_index(text)
    return idx < len(lines) and lines[idx] == HEADER


def inject_header(text: str) -> str:
    """Return `text` with HEADER inserted at the correct line; unchanged if already present."""
    if has_header(text):
        return text
    idx = header_line_index(text)
    lines = text.splitlines()
    lines.insert(idx, HEADER)
    body = "\n".join(lines)
    # Preserve a trailing newline if the original file had one (or is non-empty).
    if text.endswith("\n") or text == "":
        body += "\n"
    return body


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify only; do not modify files; exit 1 if any file is missing the header",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    files = find_js_files(repo_root)

    if args.check:
        missing = [f for f in files if not has_header(f.read_text(encoding="utf-8"))]
        if missing:
            for f in missing:
                print(f"error: missing {HEADER!r} header: {f.relative_to(repo_root)}", file=sys.stderr)
            return 1
        print(f"generated-header check: OK ({len(files)} files)")
        return 0

    changed = 0
    for f in files:
        original = f.read_text(encoding="utf-8")
        updated = inject_header(original)
        if updated != original:
            write_atomic(f, updated)
            changed += 1
    print(f"generated-header: {changed} file(s) updated, {len(files) - changed} already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
