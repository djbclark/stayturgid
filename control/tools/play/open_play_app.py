#!/usr/bin/env python3
"""Open an app's Play/Aurora details page on device (manual install fallback).

Usage: ./open_play_app.py <p7a|s24|hd8|serial> <package.id>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402

AURORA = os.environ.get("AURORA_PKG", "com.aurora.store")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        sys.stderr.write("usage: open_play_app.py <host|serial> <package>\n")
        return 2
    serial = adb.resolve_target(argv[0])
    pkg = argv[1]
    primary = adb.adb(
        serial,
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        f"market://details?id={pkg}",
        "-n",
        f"{AURORA}/.MainActivity",
    )
    if primary.returncode != 0:
        adb.adb(
            serial,
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"market://details?id={pkg}",
        )
    print(f"Opened market://details?id={pkg} on {serial} (confirm in Aurora Store)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
