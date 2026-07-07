#!/usr/bin/env python3
"""Deploy the stayturgid AutoJs6 project to a phone over ADB.

Usage: ./deploy.py <serial|s24|hd8|p7a> [device-id]

Does NOT install AutoJs6 — use setup_autojs6.py or Obtainium first.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as adb  # noqa: E402

AUTOJS_SRC = REPO_ROOT / "autojs6"
TARGET_BASE = adb.AUTOJS_PROJECT_BASE


def deploy_project(alias: str, device_id: str = "") -> int:
    serial = adb.resolve_target(alias)
    if device_id:
        print(f"NOTE: device-id arg is deprecated; profile comes from Ansible inventory (ignored: {device_id})")

    print(f"Deploying autojs6/ → {serial}:{TARGET_BASE}")
    adb.adb(
        serial,
        "shell",
        f"mkdir -p '{TARGET_BASE}/lib' '{TARGET_BASE}/scripts'",
        check=False,
    )
    for local, remote in (
        (AUTOJS_SRC / "project.json", f"{TARGET_BASE}/project.json"),
        (AUTOJS_SRC / "main.js", f"{TARGET_BASE}/main.js"),
    ):
        adb.adb(serial, "push", str(local), remote, check=True)
    adb.adb(serial, "push", str(AUTOJS_SRC / "lib" / "."), f"{TARGET_BASE}/lib/", check=True)
    adb.adb(serial, "push", str(AUTOJS_SRC / "scripts" / "."), f"{TARGET_BASE}/scripts/", check=True)

    print(f"Done. In AutoJs6: open project {TARGET_BASE} → run main.js")
    print(f"Then: ./set_automation_mode.py {alias} && ./start_watchdog.py {alias}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: deploy.py <serial|s24|hd8|p7a> [device-id]\n")
        return 2
    device_id = argv[1] if len(argv) > 1 else ""
    try:
        return deploy_project(argv[0], device_id)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"ERROR: adb failed (exit {exc.returncode})\n")
        return exc.returncode or 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
