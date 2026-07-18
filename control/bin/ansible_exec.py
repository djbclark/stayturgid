#!/usr/bin/env python3
"""Run an Ansible playbook with the active site-overlay configuration.

This is the small bridge used by direct ``just`` recipes.  It gives those
recipes the same ANSIBLE_CONFIG precedence as ``deploy_fleet.py`` while still
pinning product assets to this checkout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib.ansible_context import AnsibleConfigError, require_inventory, resolve_ansible_context


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "ansible-playbook":
        print("Usage: ansible_exec.py ansible-playbook <playbook> [arguments...]", file=sys.stderr)
        return 2

    try:
        context = resolve_ansible_context(REPO_ROOT)
        require_inventory(context)
    except AnsibleConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(context.config)
    env["STAYTURGID_ROOT"] = str(REPO_ROOT)
    command = ["ansible-playbook", "-e", f"stayturgid_repo_root={REPO_ROOT}", *args[1:]]
    try:
        return subprocess.run(command, cwd=REPO_ROOT, env=env).returncode
    except FileNotFoundError:
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
