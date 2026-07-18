#!/usr/bin/env python3
"""Launch stayturgid AutoJs6 watchdog (main.js) on a phone.

Usage: ./start_watchdog.py <stock-android-device|oneui-device|fireos-device|serial>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402

MAIN = f"{adb.AUTOJS_PROJECT_BASE}/main.js"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write(
            "usage: start_watchdog.py <stock-android-device|oneui-device|fireos-device|serial> [adb_serial]\n"
        )
        return 2
    serial = argv[1] if len(argv) > 1 else adb.resolve_target(argv[0])
    # Fire OS (fireos-device) can leave AutoJs6 stuck — am start delivers intent to the
    # zombie instance without actually running the script.  -S force-stops first
    # so the RunIntentActivity starts clean.  Harmless on phone OS too.
    is_fire = "fireos-device" in (argv[0] if argv else "") or "fire" in serial.lower()
    print(f"Starting main.js on {serial}{'  (force-stop first)' if is_fire else ''}...")
    adb.start_autojs_file(serial, MAIN, force_stop=is_fire)
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
