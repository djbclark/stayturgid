#!/usr/bin/env python3
"""Write stayturgid automation marker and sync Shizuku grants for AutoJs6.

Usage: ./set_automation_mode.py <serial|s24|hd8|p7a>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402

GRANT = Path(__file__).resolve().parent / "grant_shizuku.py"
ENABLE = Path(__file__).resolve().parent / "enable_autojs6_shizuku.py"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: set_automation_mode.py <serial|s24|hd8|p7a>\n")
        return 2
    alias = argv[0]
    serial = adb.resolve_target(alias)
    adb.adb(serial, "shell", "echo autojs6 > /sdcard/stayturgid/state/automation_mode.txt", check=False)
    print(f"Wrote automation mode autojs6 on {serial}")

    if ENABLE.is_file():
        print("Enabling AutoJs6 (accessibility + Shizuku drawer)...")
        rc = subprocess.run([sys.executable, str(ENABLE), alias]).returncode
        if rc != 0:
            print("WARN: enable_autojs6_shizuku failed — see debug bundle in stderr", file=sys.stderr)
    elif GRANT.is_file():
        print("Syncing Shizuku authorized apps for AutoJs6...")
        rc = subprocess.run([sys.executable, str(GRANT), alias]).returncode
        if rc != 0:
            print("WARN: Shizuku grant sync failed (is Shizuku up?)", file=sys.stderr)
    print(
        f"""
Next steps on device:
  1. ./start_watchdog.py {alias}   # or run main.js in AutoJs6
  2. Optional: AutoJs6 timed task every 20 min + run on boot for main.js
"""
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
