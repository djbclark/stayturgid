#!/usr/bin/env python3
"""Grant Shizuku API access to stayturgid-agent (native Kotlin APK).

`pm grant`, then a conditional Shizuku server restart (only if one is already
running) so the grant takes effect immediately. ShizukuConfigManager's
in-memory authorization state -- and shizuku.json's cached flags -- are only
ever reconciled from the real `pm grant`/`pm revoke` state at server
*startup*; hand-patching shizuku.json (the old approach here) has no live
effect on an already-running server, so this no longer touches that file.

Usage:
  ./grant_shizuku.py <host-or-serial> [package]

Default package is the debug build: org.stayturgid.agent.debug
Release package: org.stayturgid.agent
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402

DEFAULT_PKG = "org.stayturgid.agent.debug"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write(f"usage: grant_shizuku.py <host-or-serial> [package]\n  default package: {DEFAULT_PKG}\n")
        return 2
    target = argv[0]
    pkg = argv[1] if len(argv) > 1 else DEFAULT_PKG
    shell = dev.PrivShell(target)

    uid = shell.app_uid(pkg)
    if not uid:
        sys.stderr.write(f"ERROR: could not resolve uid for {pkg}\n")
        return 1

    if shell.is_permission_granted(pkg, SHIZUKU_PERM):
        print(f"Shizuku: {pkg} (uid={uid}) already granted on {shell.target}")
        return 0

    rc, out = shell.sh(f"pm grant {pkg} {SHIZUKU_PERM}")
    if rc != 0:
        sys.stderr.write(f"ERROR: pm grant {pkg} {SHIZUKU_PERM} failed: {out}\n")
        return 1

    attempted, restart_ok = shell.restart_shizuku_if_running()
    if attempted and not restart_ok:
        print(f"WARN: granted {pkg} (uid={uid}) but the Shizuku server restart failed")
        print("      grant will only take effect on the next natural restart")
        return 1

    print(f"Shizuku: allowed {pkg} (uid={uid}) on {shell.target}" + (" (restarted server)" if attempted else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
