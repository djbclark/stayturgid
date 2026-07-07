#!/usr/bin/env python3
"""Push stayturgid Obtainium configs to a phone and import via deep link.

Usage:
  ./sync_to_device.py <s24|p7a|hd8|serial> [all|autojs6] [--no-import]

Re-importing merges/updates existing entries (does not remove other apps).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as adb  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
IMPORT_SCRIPT = Path(__file__).resolve().parent / "import_catalog.py"
CATALOGS = {
    "all": (REPO_ROOT / "obtainium" / "stayturgid-apps.json", "stayturgid-obtainium-apps.json"),
    "autojs6": (REPO_ROOT / "obtainium" / "autojs6-only.json", "stayturgid-obtainium-autojs6.json"),
}


def sync_catalog(alias: str, which: str = "all", *, import_catalog: bool = True) -> int:
    if which not in CATALOGS:
        sys.stderr.write("second arg must be all or autojs6\n")
        return 2
    serial = adb.resolve_target(alias)
    if not adb.package_installed(serial, OBTAINIUM_PKG):
        sys.stderr.write(f"ERROR: Obtainium ({OBTAINIUM_PKG}) not installed on {serial}\n")
        sys.stderr.write("Install from https://github.com/ImranR98/Obtainium/releases\n")
        return 1

    json_path, dest_name = CATALOGS[which]
    remote = f"/sdcard/Download/{dest_name}"
    print(f"Pushing {json_path} → {serial}:{remote}")
    adb.adb(serial, "push", str(json_path), remote, check=True)

    if not import_catalog:
        print(f"Skipped import (--no-import). JSON at Download/{dest_name}")
        return 0
    if not IMPORT_SCRIPT.is_file():
        print(f"WARN: {IMPORT_SCRIPT} missing — JSON pushed only.", file=sys.stderr)
        return 0

    print(f"Importing catalog into Obtainium on {serial}...")
    return subprocess.run([sys.executable, str(IMPORT_SCRIPT), alias, which], cwd=REPO_ROOT).returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        sys.stderr.write(
            "usage: sync_to_device.py <p7a|s24|hd8|serial> [all|autojs6] [--no-import]\n"
        )
        return 2

    no_import = "--no-import" in argv
    argv = [a for a in argv if a != "--no-import"]
    alias = argv[0]
    which = "all"
    if len(argv) > 1 and argv[1] != "--no-import":
        which = argv[1]
    try:
        return sync_catalog(alias, which, import_catalog=not no_import)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"ERROR: adb failed (exit {exc.returncode})\n")
        return exc.returncode or 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
