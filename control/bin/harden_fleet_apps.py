#!/usr/bin/env python3
"""Apply stayturgid fleet app privileges over adb (Mac-side).

Grants runtime permissions, disables unused-app restrictions, and applies
per-package battery policy from control/lib/fleet_app_profiles.json (most fleet
apps are Doze-whitelisted; Aurora Store stays battery-optimized). Mirrors
android_common.app_privileges Ansible role.

Usage: ./harden_fleet_apps.py <oneui-device|stock-android-device|fireos-device|serial>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_JSON = REPO_ROOT / "control" / "lib" / "fleet_app_profiles.json"
COLLECTION = REPO_ROOT / "ansible_collections" / "stayturgid" / "android_common"

sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
sys.path.insert(0, str(COLLECTION / "plugins" / "module_utils"))
import fleet_privileges as fp  # noqa: E402
import stayturgid_device as dev  # noqa: E402


def load_profiles() -> list[dict]:
    if not PROFILES_JSON.is_file():
        raise SystemExit("missing %s" % PROFILES_JSON)
    return json.loads(PROFILES_JSON.read_text())


def adb_run(cmd: list[str], **kwargs) -> tuple[int, str, str]:
    if cmd and cmd[0] == "adb":
        cmd[0] = dev.adb_bin()
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout, result.stderr


def run_command(cmd, **kwargs):
    if isinstance(cmd, str):
        cmd = cmd.split()
    return adb_run(cmd, **kwargs)


def summarize(results: list[dict]) -> None:
    for entry in results:
        pkg = entry.get("package", "?")
        if entry.get("status") == "skipped":
            print("  skip %s (not installed)" % pkg)
            continue
        for item in entry.get("items") or []:
            kind = item.get("kind", "item")
            detail = item.get("op") or item.get("permission") or ""
            status = item.get("status", "")
            if status not in ("already", "skipped"):
                print("  %s %s %s -> %s" % (pkg, kind, detail, status))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: harden_fleet_apps.py <oneui-device|stock-android-device|fireos-device|serial>\n")
        return 2

    alias = argv[0]
    serial = dev.resolve_adb(alias)
    subprocess.run([dev.adb_bin(), "connect", serial], capture_output=True, text=True)

    profiles = load_profiles()
    print("Hardening %d fleet app profile(s) on %s..." % (len(profiles), alias))
    changed, results = fp.apply_profiles(run_command, serial, profiles)
    summarize(results)
    print("Fleet app hardening %s on %s." % ("applied changes" if changed else "already satisfied", alias))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
