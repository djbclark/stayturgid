"""Resolve fleet targets from the active Ansible inventory.

The inventory is the authoritative source for a device's fleet status.  Entry
points with a default "all devices" mode use this module so an ``offline``
mark excludes a device consistently.  Explicit command-line hosts are an
intentional operator override.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .ansible_context import require_inventory, resolve_ansible_context, resolved_env

FLEET_STATUS_VAR = "stayturgid_fleet_status"


def parse_inventory_hosts(data: dict, group: str = "stayturgid") -> list[str]:
    """Return host names in *group* while preserving inventory order."""

    hosts = data[group]["hosts"]
    if isinstance(hosts, list):
        return list(hosts)
    return list(hosts.keys())


def inventory_list(repo_root: Path, group: str = "stayturgid") -> dict:
    """Load the selected site's evaluated Ansible inventory."""

    context = resolve_ansible_context(repo_root)
    require_inventory(context)
    result = subprocess.run(
        ["ansible-inventory", *context.inventory_args(), "--list"],
        capture_output=True,
        text=True,
        check=True,
        env=resolved_env(repo_root),
        cwd=repo_root,
    )
    return json.loads(result.stdout)


def offline_hosts(data: dict, hosts: list[str]) -> list[str]:
    """Return hosts whose authoritative fleet status is ``offline``."""

    hostvars = data.get("_meta", {}).get("hostvars", {})
    return [host for host in hosts if hostvars.get(host, {}).get(FLEET_STATUS_VAR) == "offline"]


def resolve_hosts(
    explicit_hosts: list[str],
    *,
    repo_root: Path,
    command_name: str,
) -> list[str]:
    """Resolve default targets, omitting offline inventory hosts.

    Explicit hosts retain deploy_fleet.py's established override contract.
    """

    if explicit_hosts:
        return explicit_hosts
    data = inventory_list(repo_root)
    hosts = parse_inventory_hosts(data)
    skipped = offline_hosts(data, hosts)
    if skipped:
        print(
            f"{command_name}: skipping offline host(s) {', '.join(skipped)} "
            f"({FLEET_STATUS_VAR}: offline) — pass explicitly to override",
            file=sys.stderr,
        )
    return [host for host in hosts if host not in skipped]
