#!/usr/bin/env python3
"""Launch stayturgid AutoJs6 watchdog (main.js) on a phone.

Usage: ./start_watchdog.py <p7a|s24|hd8|serial>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as adb  # noqa: E402

MAIN = f"{adb.AUTOJS_PROJECT_BASE}/main.js"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: start_watchdog.py <p7a|s24|hd8|serial>\n")
        return 2
    serial = adb.resolve_target(argv[0])
    print(f"Starting main.js on {serial}...")
    adb.start_autojs_file(serial, MAIN)
    time.sleep(3)
    tail = adb.adb(
        serial,
        "shell",
        "grep 'autojs6' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -3",
    )
    if tail.stdout:
        print(tail.stdout.rstrip())
    print("Check AutoJs6 → Task tab → Running task should show main.js")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
