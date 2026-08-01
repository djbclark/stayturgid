#!/usr/bin/env python3
"""Run an Ansible playbook with the active site-overlay configuration.

This is the small bridge used by direct ``just`` recipes.  It gives those
recipes the same ANSIBLE_CONFIG precedence as ``deploy_fleet.py`` while still
pinning product assets to this checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib.ansible_context import (
    AnsibleConfigError,
    require_inventory,
    resolve_ansible_context,
    resolved_env,
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "ansible-playbook":
        print("Usage: ansible_exec.py ansible-playbook <playbook> [arguments...]", file=sys.stderr)
        return 2

    try:
        # Silent resolve for the inventory preflight; resolved_env() re-resolves
        # (announcing once) and — crucially — also pins ANSIBLE_ROLES_PATH and
        # ANSIBLE_COLLECTIONS_PATH to this checkout. Without those, a site
        # overlay whose ansible.cfg omits product paths (the norm) can't find
        # the product roles/collections, so e.g. `just deploy-mac` failed with
        # "role 'control_node' was not found". Matches deploy_fleet.py.
        context = resolve_ansible_context(REPO_ROOT, announce=False)
        require_inventory(context)
        env = resolved_env(REPO_ROOT)
    except AnsibleConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    command = ["ansible-playbook", "-e", f"stayturgid_repo_root={REPO_ROOT}", *args[1:]]
    try:
        return subprocess.run(command, cwd=REPO_ROOT, env=env).returncode
    except FileNotFoundError:
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
