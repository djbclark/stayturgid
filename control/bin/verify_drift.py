#!/usr/bin/env python3
"""Run stayturgid verification + drift detection via Ansible.

Usage:
  python3 control/bin/verify_drift.py [--host oneui-device] [--all]
  just verify-drift HOSTS=oneui-device
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet" / "verify-drift.yml"

sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
from ansible_context import (  # noqa: E402
    AnsibleConfigError,
    require_limit_hosts,
    resolve_ansible_context,
    resolved_env,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify stayturgid device state")
    parser.add_argument("--host", help="Single host alias (oneui-device, stock-android-device, fireos-device)")
    parser.add_argument("--all", action="store_true", help="Verify all fleet devices")
    args = parser.parse_args(argv)

    if args.host:
        hosts = args.host
    elif args.all:
        hosts = "stayturgid"
    else:
        print("Specify --host <alias> or --all")
        return 1

    try:
        context = resolve_ansible_context(REPO_ROOT)
        require_limit_hosts(context, hosts)
        env = resolved_env(REPO_ROOT)
    except AnsibleConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    env["ANSIBLE_STDOUT_CALLBACK"] = "default"

    proc = subprocess.run(
        ["ansible-playbook", str(PLAYBOOK), "-l", hosts],
        env=env,
        timeout=120,
    )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
