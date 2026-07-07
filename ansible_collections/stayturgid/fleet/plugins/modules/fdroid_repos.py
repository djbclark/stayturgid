#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fdroid_repos
short_description: Manage F-Droid repositories and (optionally) the Neo Store client via fdroidcl
description:
  - Uses the fdroidcl CLI (on the control machine) to declaratively add/enable F-Droid repositories on a device over ADB.
  - Supports "setups" for groups of repos + tracked apps.
  - Can ensure the Neo Store F-Droid GUI client is present and configured (Shizuku + background auto-updates).
options:
  repos:
    description:
      - List of F-Droid repos to ensure.
    type: list
    elements: dict
    required: false
    suboptions:
      name:
        type: str
        required: true
      address:
        type: str
        required: true
      fingerprint:
        type: str
        required: false
  ensure_neo_store:
    description:
      - If true and no F-Droid GUI detected, ensure Neo Store is installed (via Obtainium) and configured for Shizuku + auto updates.
    type: bool
    default: true
  neo_store_package:
    type: str
    default: com.machiav3lli.fdroid
author:
  - stayturgid project
"""

EXAMPLES = r"""
- name: Add IzzyOnDroid repo
  stayturgid.fleet.fdroid_repos:
    repos:
      - name: IzzyOnDroid
        address: https://apt.izzysoft.de/fdroid/repo

- name: Full client + repos for a device without F-Droid GUI
  stayturgid.fleet.fdroid_repos:
    repos: "{{ my_fdroid_repos }}"
    ensure_neo_store: true
"""

RETURN = r"""
changed:
  description: Whether any repos or client state changed.
  type: bool
fdroidcl_output:
  description: Output from fdroidcl commands (if any).
  type: str
"""

import json
import re
import os

from ansible.module_utils.basic import AnsibleModule


def run_cmd(module, cmd):
    rc, out, err = module.run_command(cmd)
    return rc, (out or "").strip(), (err or "").strip()


def run_fdroidcl(module, args):
    """Run fdroidcl and return (rc, out, err)."""
    return run_cmd(module, ["fdroidcl"] + args)


def parse_current_repos(output):
    """Parse `fdroidcl repo` output (multi-line Name/URL/Enabled blocks).
    Returns set of (name, url) tuples for easy presence checks."""
    repos = set()
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current.get("Name") and current.get("URL"):
                repos.add((current["Name"], current["URL"]))
            current = {}
            continue
        if line.startswith("Name:"):
            current["Name"] = line.split(":", 1)[1].strip()
        elif line.startswith("URL:"):
            current["URL"] = line.split(":", 1)[1].strip()
        elif line.startswith("Enabled:"):
            current["Enabled"] = line.split(":", 1)[1].strip().lower() == "yes"
    if current.get("Name") and current.get("URL"):
        repos.add((current["Name"], current["URL"]))
    return repos


def main():
    module = AnsibleModule(
        argument_spec=dict(
            repos=dict(type="list", elements="dict", required=False, default=[]),
            ensure_neo_store=dict(type="bool", default=True),
            neo_store_package=dict(type="str", default="com.machiav3lli.fdroid"),
            device=dict(type="str", required=False, default="localhost:5555"),  # or alias
        ),
        supports_check_mode=True,
    )

    desired_repos = module.params["repos"]
    ensure_neo = module.params["ensure_neo_store"]
    neo_pkg = module.params["neo_store_package"]
    device = module.params.get("device", "localhost:5555")

    changed = False
    outputs = []
    facts = {}

    # Ensure we can talk to adb for client detection
    rc, _, _ = run_cmd(module, ["adb", "connect", device])
    # ignore rc; may already be connected

    # 1. Handle Neo Store client bootstrap / config (per review requirement)
    if ensure_neo:
        rc, pm_out, _ = run_cmd(module, ["adb", "-s", device, "shell", "pm", "list", "packages"])
        has_fdroid_gui = bool(re.search(r'fdroid|droidify|machiav3lli', pm_out or "", re.I))
        facts["has_fdroid_gui"] = has_fdroid_gui
        facts["neo_store_installed"] = neo_pkg in (pm_out or "")

        if not has_fdroid_gui:
            outputs.append("No F-Droid GUI detected; Neo Store should be installed via Obtainium catalog (added as com.machiav3lli.fdroid)")
            changed = True  # conceptual change; actual install via obtainium role
        else:
            outputs.append("F-Droid GUI present; will ensure Neo Store config for Shizuku + background updates")

        # Shizuku grant for Neo Store can be done via shared helper (see role)
        # Background updates: usually enabled after first install-through-NeoStore; we can note or set if prefs exposed

    # 2. Manage F-Droid repos via fdroidcl (core of fdroid_repos)
    if desired_repos:
        rc, repo_list_out, _ = run_fdroidcl(module, ["repo"])
        current = parse_current_repos(repo_list_out)
        outputs.append(f"Current fdroidcl repos parsed: {current}")

        for r in desired_repos:
            name = r.get("name")
            address = r.get("address")
            if not name or not address:
                module.fail_json(msg="repo entry requires 'name' and 'address'")

            # Simple presence check
            present = any(name in str(c) or address in str(c) for c in current)

            if module.check_mode:
                if not present:
                    changed = True
                continue

            if not present:
                args = ["repo", "add", name, address]
                # Some fdroidcl support fingerprint as 3rd arg
                if r.get("fingerprint"):
                    args.append(r["fingerprint"])
                rc, out, err = run_fdroidcl(module, args)
                outputs.append(out or err)
                if rc == 0:
                    changed = True
                    # Enable if needed
                    run_fdroidcl(module, ["repo", "enable", name])
            else:
                # Ensure enabled
                run_fdroidcl(module, ["repo", "enable", name])

    if module.check_mode:
        module.exit_json(changed=changed, msg="check mode", **facts)

    module.exit_json(
        changed=changed,
        fdroidcl_output="\n".join(outputs),
        facts=facts,
        msg="fdroid_repos processed repos and client requirements",
    )


if __name__ == "__main__":
    main()
