#!/usr/bin/env python3
"""Headlessly nudge stayturgid native-agent HostService on a device.

The exported PeerStartReceiver starts the foreground service from app context.
Never use MainActivity for unattended recovery: it interrupts the operator's
foreground task (#199).

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
PEER_START_RECEIVER = "org.stayturgid.agent.PeerStartReceiver"
PEER_START_ACTION = "org.stayturgid.agent.action.PEER_START_NOW"


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
    component = f"{pkg}/{PEER_START_RECEIVER}"
    print(f"Headlessly starting native-agent on {serial} ({component})...")
    r = adb.adb(
        serial,
        "shell",
        f"am broadcast --include-stopped-packages -a {PEER_START_ACTION} -n {component}",
    )
    if r.returncode != 0:
        sys.stderr.write((r.stderr or r.stdout or "peer-start broadcast failed").strip() + "\n")
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
