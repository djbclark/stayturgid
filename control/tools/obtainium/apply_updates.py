#!/usr/bin/env python3
"""Trigger Obtainium headless update check via deep-link (no UI automation).

Uses djbclark/Obtainium fork's headless update deep-link:
  obtainium://update/all?autoInstall=true&headless=true

No screen control, no tap automation, no installer dialog handling needed.
The fork handles Shizuku silent install internally.

Usage: ./apply_updates.py <p7a|s24|hd8|serial>
"""
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
RESULT_FILE = "/data/data/%s/app_flutter/headless_result.json" % OBTAINIUM_PKG


def adb(serial, *args, timeout=30):
    try:
        return subprocess.run(
            ["adb", "-s", serial, "shell"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: apply_updates.py <p7a|s24|hd8|serial>\n")
        return 2
    host = argv[0]
    serial = dev.resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    # Send headless update deep-link with auto-install.
    adb(serial, "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", "obtainium://update/all?autoInstall=true&headless=true")
    print("Headless update triggered — waiting up to 90s...")

    # Poll for headless_result.json.
    deadline = time.time() + 90
    result = None
    while time.time() < deadline:
        time.sleep(5)
        r = adb(serial, "cat", RESULT_FILE)
        if r and r.returncode == 0 and r.stdout and r.stdout.strip():
            result = r.stdout.strip()
            break

    if result:
        try:
            parsed = json.loads(result)
            updated = parsed.get("updatedCount", parsed.get("updated", 0))
            failed = parsed.get("failedCount", parsed.get("failed", 0))
            skipped = parsed.get("skippedCount", parsed.get("skipped", 0))
            print("Update complete: %d updated, %d failed, %d skipped" % (updated, failed, skipped))
        except (json.JSONDecodeError, KeyError):
            print("Update result: %s" % result[:200])
        return 0

    print("Update check sent (no result file — may still be running or fork not yet installed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
