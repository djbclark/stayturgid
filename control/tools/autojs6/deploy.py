#!/usr/bin/env python3
"""Deploy the stayturgid AutoJs6 project to a phone over ADB.

Usage: ./deploy.py <serial|s24|hd8|p7a> [device-id]

Does NOT install AutoJs6 — use setup_autojs6.py or Obtainium first.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
_COLLECTION_UTILS = REPO_ROOT / "ansible_collections" / "stayturgid" / "android_common" / "plugins" / "module_utils"
if str(_COLLECTION_UTILS) not in sys.path:
    sys.path.insert(0, str(_COLLECTION_UTILS))

import adb_cli as adb  # noqa: E402
import adb_shell  # noqa: E402
import autojs6_deploy_util as deploy_util  # noqa: E402


def _run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout or "", result.stderr or ""


def deploy_project(alias: str, device_id: str = "") -> int:
    serial = adb.resolve_target(alias)
    if device_id:
        print(f"NOTE: device-id arg is deprecated; profile comes from Ansible inventory (ignored: {device_id})")

    print(f"Deploying device/autojs6/ → {serial}:{deploy_util.DEFAULT_TARGET}")
    adb_shell.adb_connect(_run_command, serial)

    ok, msg, _changed = deploy_util.deploy_project(
        _run_command,
        serial,
        str(REPO_ROOT),
        target=deploy_util.DEFAULT_TARGET,
    )
    if not ok:
        sys.stderr.write("ERROR: %s\n" % msg)
        return 1

    print(f"Done. In AutoJs6: open project {deploy_util.DEFAULT_TARGET} → run main.js")
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
