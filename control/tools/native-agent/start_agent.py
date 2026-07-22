#!/usr/bin/env python3
"""Start stayturgid native-agent HostService on a device.

FGS cannot be started from adb shell on API 34+; launch MainActivity which
auto-starts HostService in app context.

Usage: ./start_agent.py <host-or-serial> [adb_serial]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402

PKG_DEBUG = "org.stayturgid.agent.debug"
PKG_RELEASE = "org.stayturgid.agent"
ACTIVITY = "org.stayturgid.agent.MainActivity"


def _resolve_pkg(serial: str) -> str | None:
    for pkg in (PKG_DEBUG, PKG_RELEASE):
        r = adb.adb(serial, "shell", f"pm path {pkg}")
        if r.returncode == 0 and (r.stdout or "").strip():
            return pkg
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: start_agent.py <host-or-serial> [adb_serial]\n")
        return 2
    serial = argv[1] if len(argv) > 1 else adb.resolve_target(argv[0])
    pkg = _resolve_pkg(serial)
    if not pkg:
        sys.stderr.write(f"ERROR: neither {PKG_DEBUG} nor {PKG_RELEASE} installed on {serial}\n")
        return 1
    component = f"{pkg}/{ACTIVITY}"
    print(f"Starting native-agent on {serial} ({component})...")
    # Force-stop first so FGS + UserService restart cleanly after freezes.
    adb.adb(serial, "shell", f"am force-stop {pkg}")
    time.sleep(1)
    r = adb.adb(serial, "shell", f"am start -n {component}")
    if r.returncode != 0:
        sys.stderr.write((r.stderr or r.stdout or "am start failed").strip() + "\n")
        return 1
    time.sleep(4)
    pid = adb.adb(serial, "shell", f"pidof {pkg}").stdout or ""
    us = adb.adb(serial, "shell", f"pidof {pkg}:userservice").stdout or ""
    print(f"host_pid={(pid or '').strip() or 'none'} userservice={(us or '').strip() or 'none'}")
    tail = adb.adb(
        serial,
        "shell",
        "tail -3 /sdcard/stayturgid/logs/agent.log 2>/dev/null",
    )
    if tail.stdout:
        print(tail.stdout.rstrip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
