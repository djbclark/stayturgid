#!/usr/bin/env python3
"""Resolve stayturgid repo root from any module script depth."""
from __future__ import annotations

import sys
from pathlib import Path


def stayturgid_root(script: str | Path) -> Path:
    """Walk up from *script* until ``device/termux/`` and ``control/lib/`` exist."""
    path = Path(script).resolve()
    if path.is_file():
        path = path.parent
    while path != path.parent:
        if (path / "device" / "termux").is_dir() and (path / "control" / "lib").is_dir():
            return path
        # Legacy layout (pre-restructure)
        if (path / "termux").is_dir() and (path / "shared").is_dir():
            return path
        path = path.parent
    raise SystemExit(
        "ERROR: stayturgid repo root not found (walked up from %s)" % script
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: stayturgid_root.py /path/to/calling/script.py\n")
        return 2
    print(stayturgid_root(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
