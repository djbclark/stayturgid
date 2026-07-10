#!/usr/bin/env python3
"""Run a single AutoJs6 test script on a phone.

Usage: ./run_test.py <p7a|s24|hd8|serial> <script.js>

Examples:
  ./run_test.py s24 test-watchdog-once.js
  ./run_test.py s24 test-tailscale-probe-once.js
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402

SCRIPTS_BASE = f"{adb.AUTOJS_PROJECT_BASE}/scripts"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        sys.stderr.write("usage: run_test.py <p7a|s24|hd8|serial> <script.js>\n")
        return 2
    serial = adb.resolve_target(argv[0])
    script = argv[1]
    print(f"Running {script} on {serial}...")
    adb.start_autojs_file(serial, f"{SCRIPTS_BASE}/{script}")
    time.sleep(3)
    print("Tail of watchdog log:")
    tail = adb.adb(serial, "shell", "tail -8 /sdcard/stayturgid/logs/watchdog.log 2>/dev/null")
    if tail.stdout:
        print(tail.stdout.rstrip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
