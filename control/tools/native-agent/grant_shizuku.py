#!/usr/bin/env python3
"""Grant Shizuku API access to stayturgid-agent (native Kotlin APK).

Same mechanism as control/tools/autojs6/grant_shizuku.py: pm grant + patch
/data/local/tmp/shizuku/shizuku.json. Restart Shizuku after if the app still
sees permission denied:

  adb -s <serial> shell /data/local/tmp/shizuku_starter

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
SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku.json"


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

    shell.sh(f"pm grant {pkg} {SHIZUKU_PERM}")

    current, ok = shell.read_shizuku_json(SHIZUKU_JSON)
    if not ok:
        sys.stderr.write(f"ERROR: no privileged shell or unreadable {SHIZUKU_JSON} — aborting\n")
        return 1

    patched = dev.patch_shizuku_json(current, uid, pkg)
    if not shell.install_shizuku_json(patched, STAGING, SHIZUKU_JSON):
        sys.stderr.write("ERROR: failed to install patched shizuku.json\n")
        return 1

    print(f"Shizuku: allowed {pkg} (uid={uid}) on {shell.target}")
    print("If the app still reports denied, restart Shizuku (shizuku_starter).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
