#!/usr/bin/env python3
"""Import Obtainium catalog — headless via deep-link (no UI automation).

Uses djbclark/Obtainium fork's headless import with ?confirm=true to
bypass the confirmation dialog and &headless=true to exit after import.

Usage:
  ./import_catalog.py <p7a|s24|hd8|serial> [all|autojs6|/path/to.json]
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
CATALOGS = {
    "all": os.path.join(REPO, "catalogs", "obtainium", "stayturgid-apps.json"),
    "autojs6": os.path.join(REPO, "catalogs", "obtainium", "autojs6-only.json"),
}


def load_catalog(path):
    with open(path) as f:
        data = json.load(f)
    apps = data.get("apps")
    if not apps:
        raise ValueError("catalog has no apps: %s" % path)
    return apps


def adb_shell(serial, *args, timeout=30):
    try:
        return subprocess.run(
            ["adb", "-s", serial, "shell"] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_import_uri(apps):
    encoded = urllib.parse.quote(json.dumps(apps, separators=(",", ":")))
    return "obtainium://apps/%s?confirm=true&headless=true" % encoded


def import_catalog(serial, catalog_path):
    apps = load_catalog(catalog_path)
    uri = build_import_uri(apps)

    adb_shell(serial, "am", "force-stop", OBTAINIUM_PKG)
    time.sleep(0.5)
    adb_shell(
        serial,
        "am",
        "start",
        "-f",
        "0x10200000",  # FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_CLEAR_TOP
        "-a",
        "android.intent.action.VIEW",
        "-d",
        uri,
    )
    time.sleep(4)

    # Check headless_result.json for confirmation.
    result = adb_shell(serial, "cat", "/data/data/%s/app_flutter/headless_result.json" % OBTAINIUM_PKG)
    if result and result.returncode == 0 and result.stdout:
        print("Import result: %s" % result.stdout.strip()[:200])
    else:
        print("Import URI sent to Obtainium on %s (%d apps)." % (serial, len(apps)))
    return True


def resolve_catalog(which):
    if which in CATALOGS:
        return CATALOGS[which]
    if os.path.isfile(which):
        return which
    raise ValueError("unknown catalog %r (use all, autojs6, or a .json path)" % which)


def main(host, which):
    serial = dev.resolve_adb(host)
    try:
        catalog_path = resolve_catalog(which)
    except ValueError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 2

    result = adb_shell(serial, "pm", "path", OBTAINIUM_PKG)
    if not result or not (result.stdout or "").strip():
        sys.stderr.write("ERROR: Obtainium not installed on %s\n" % serial)
        return 1

    adb_shell(serial, "wait-for-device")
    if not import_catalog(serial, catalog_path):
        return 1
    return 0


def main_cli(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: import_catalog.py <p7a|s24|hd8|serial> [all|autojs6|path.json]\n")
        return 2

    host = argv[0]
    which = argv[1] if len(argv) > 1 else "all"
    return main(host, which)


if __name__ == "__main__":
    sys.exit(main_cli())
