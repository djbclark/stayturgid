#!/usr/bin/env python3
"""Mac-side backup/restore for enabled_accessibility_services.

Usage:
  ./control/bin/a11y_services.py backup <s24|p7a|hd8|serial>
  ./control/bin/a11y_services.py restore <s24|p7a|hd8|serial> [--profile|--backup|--merge]
  ./control/bin/a11y_services.py show <s24|p7a|hd8|serial>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import a11y_services as a11y  # noqa: E402
import stayturgid_device as dev  # noqa: E402

SD_ROOT = "/sdcard/stayturgid"


def adb(serial: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, "shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
    )


def get_services(serial: str) -> str:
    return (adb(serial, "settings", "get", "secure", "enabled_accessibility_services").stdout or "").strip()


def put_services(serial: str, value: str) -> None:
    adb(serial, "settings", "put", "secure", "enabled_accessibility_services", value)
    adb(serial, "settings", "put", "secure", "accessibility_enabled", "1")


def push_device_backup(serial: str, value: str) -> None:
    path = "%s/%s" % (SD_ROOT, a11y.DEVICE_BACKUP_REL)
    adb(serial, "mkdir", "-p", "%s/state" % SD_ROOT)
    tmp = a11y.backup_file_for(".device_push")
    a11y.write_backup_file(tmp, value)
    subprocess.run(["adb", "-s", serial, "push", str(tmp), path], check=False)
    tmp.unlink(missing_ok=True)


def backup_alias(alias: str) -> int:
    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    live = get_services(serial)
    a11y.write_backup_file(a11y.backup_file_for(alias), live)
    push_device_backup(serial, live)
    print("%s: backed up %d service(s)" % (alias, len(a11y.parse_services(live))))
    for svc in a11y.parse_services(live):
        print("  %s" % svc)
    return 0


def restore_alias(alias: str, mode: str) -> int:
    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    before = get_services(serial)
    backup = a11y.read_backup_file(a11y.backup_file_for(alias))
    if mode == "profile":
        target = a11y.join_services(a11y.profile_services(alias))
    elif mode == "backup":
        target = backup or a11y.join_services(a11y.profile_services(alias))
    else:
        target = a11y.desired_services(alias, backup or before, ensure_autojs6=True)
    if not target:
        sys.stderr.write("ERROR: no restore target for %s\n" % alias)
        return 1
    put_services(serial, target)
    time.sleep(0.5)
    after = get_services(serial)
    print("%s: restored (%s)" % (alias, mode))
    print("  before: %s" % (before or "(empty)"))
    print("  after:  %s" % after)
    lost = a11y.services_lost(before, after)
    if lost:
        print("  WARN: still missing vs pre-restore: %s" % ", ".join(lost))
    return 0


def show_alias(alias: str) -> int:
    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    live = get_services(serial)
    backup = a11y.read_backup_file(a11y.backup_file_for(alias))
    profile = a11y.join_services(a11y.profile_services(alias))
    print("%s live (%d):" % (alias, len(a11y.parse_services(live))))
    for svc in a11y.parse_services(live):
        print("  %s" % svc)
    print("repo backup (%d):" % len(a11y.parse_services(backup)))
    for svc in a11y.parse_services(backup):
        print("  %s" % svc)
    print("profile (%d):" % len(a11y.parse_services(profile)))
    for svc in a11y.parse_services(profile):
        print("  %s" % svc)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup/restore accessibility service lists")
    parser.add_argument("action", choices=["backup", "restore", "show"])
    parser.add_argument("alias")
    parser.add_argument(
        "--mode",
        choices=["merge", "profile", "backup"],
        default="merge",
        help="restore source (default: merge profile+backup+live)",
    )
    args = parser.parse_args(argv)
    if args.action == "backup":
        return backup_alias(args.alias)
    if args.action == "restore":
        return restore_alias(args.alias, args.mode)
    return show_alias(args.alias)


if __name__ == "__main__":
    sys.exit(main())
