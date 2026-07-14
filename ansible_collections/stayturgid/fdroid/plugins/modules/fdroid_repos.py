#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fdroid_repos
short_description: Manage F-Droid repositories in local fdroidcl config
description:
  - Declaratively add and enable F-Droid repositories in the control machine's
    C(fdroidcl) config (C(brew install fdroidcl)).
  - Runs on the control node (delegate_to localhost). Use the C(fdroid_repos)
    role to push repos to an on-device Neo Store client and grant Shizuku.
  - Does not install Neo Store — use the C(obtainium_apps) role first.
options:
  repos:
    description: F-Droid repos to manage in fdroidcl.
    type: list
    elements: dict
    default: []
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
      state:
        description: C(present) adds and enables; C(absent) removes.
        type: str
        choices: [present, absent]
        default: present
  setups:
    description:
      - fdroidcl mass-install definitions (C(fdroidcl setup)). Each setup is
        created/updated with its repos and apps, then applied when
        C(apply_setups=true).
    type: list
    elements: dict
    default: []
    suboptions:
      name:
        type: str
        required: true
      repos:
        type: list
        elements: str
        default: []
      apps:
        type: list
        elements: str
        default: []
  apply_setups:
    description: Run C(fdroidcl setup apply) for each setup.
    type: bool
    default: true
  device:
    description:
      - ADB target (serial, host:port, or fleet alias resolved on the control
        node). Used only to verify C(adb) connectivity before mutating fdroidcl.
    type: str
    default: localhost:5555
  update_index:
    description: Run C(fdroidcl update) after any repo change.
    type: bool
    default: true
author:
  - stayturgid project
"""

EXAMPLES = r"""
- name: Ensure IzzyOnDroid in fdroidcl
  stayturgid.fdroid.fdroid_repos:
    repos:
      - name: IzzyOnDroid
        address: https://apt.izzysoft.de/fdroid/repo
        fingerprint: 3BF0D6ABFEAE2F401707B6D966BE743BF0EEE49C2561B9BA39073711F628937A
    device: p7a
"""

RETURN = r"""
changed:
  description: Whether any fdroidcl repo state changed.
  type: bool
repos:
  description: Normalized repo keys ensured.
  type: list
  elements: dict
fdroidcl_output:
  description: fdroidcl command output lines.
  type: list
  elements: str
"""

import re

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)


def normalize_url(url):
    return (url or "").strip().rstrip("/")


def normalize_fingerprint(fp):
    if not fp:
        return ""
    return re.sub(r"[^0-9A-Fa-f]", "", str(fp)).upper()


def validate_fingerprint(fp):
    """Normalized fingerprint must be empty or 64 hex chars (SHA-256)."""
    return fp == "" or len(fp) == 64


def repo_key(name, address):
    return (str(name).strip(), normalize_url(address))


def fdroidrepos_uri(address, fingerprint=None):
    """Build fdroidrepos:// intent URI for on-device F-Droid clients."""
    hostpath = re.sub(r"^https?://", "", normalize_url(address), count=1)
    uri = "fdroidrepos://" + hostpath
    fp = normalize_fingerprint(fingerprint)
    if fp:
        uri += "?fingerprint=" + fp
    return uri


def parse_current_repos(output):
    """Parse C(fdroidcl repo) output -> {(name, url): enabled_bool}."""
    repos = {}
    current = {}
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            if current.get("Name") and current.get("URL"):
                key = repo_key(current["Name"], current["URL"])
                repos[key] = current.get("Enabled", True)
            current = {}
            continue
        if line.startswith("Name:"):
            current["Name"] = line.split(":", 1)[1].strip()
        elif line.startswith("URL:"):
            current["URL"] = line.split(":", 1)[1].strip()
        elif line.startswith("Enabled:"):
            current["Enabled"] = line.split(":", 1)[1].strip().lower() == "yes"
    if current.get("Name") and current.get("URL"):
        key = repo_key(current["Name"], current["URL"])
        repos[key] = current.get("Enabled", True)
    return repos


def repo_present(current, name, address):
    return repo_key(name, address) in current


def repo_enabled(current, name, address):
    key = repo_key(name, address)
    return current.get(key, False)


def run_cmd(module, cmd):
    rc, out, err = module.run_command(cmd)
    text = ((out or "") + ("\n" + err if err else "")).strip()
    return rc, text


def run_fdroidcl(module, args):
    return run_cmd(module, ["fdroidcl"] + list(args))


def ensure_repos(module, desired, current, check_mode):
    """Return (changed, output_lines, ensured_keys)."""
    changed = False
    outputs = []
    ensured = []

    for spec in desired:
        name = spec.get("name")
        address = spec.get("address")
        state = spec.get("state", "present")
        if not name or not address:
            module.fail_json(msg="each repo requires 'name' and 'address'")
        if state not in ("present", "absent"):
            module.fail_json(msg="repo %s: state must be present or absent" % name)
        fp = normalize_fingerprint(spec.get("fingerprint"))
        if not validate_fingerprint(fp):
            module.fail_json(
                msg="repo %s: fingerprint must be 64 hex chars (got %d after normalization)" % (name, len(fp))
            )
        key = repo_key(name, address)
        ensured.append({"name": key[0], "address": key[1], "state": state})

        present = repo_present(current, name, address)
        enabled = repo_enabled(current, name, address)

        if state == "absent":
            if not present:
                continue
            changed = True
            if check_mode:
                continue
            rc, out = run_fdroidcl(module, ["repo", "remove", name])
            outputs.append(out)
            if rc != 0:
                module.fail_json(msg="fdroidcl repo remove failed for %s" % name, rc=rc, output=out)
            current.pop(key, None)
            continue

        if check_mode:
            if not present or not enabled:
                changed = True
            continue

        if not present:
            args = ["repo", "add", name, normalize_url(address)]
            if fp:
                args.append(fp)
            rc, out = run_fdroidcl(module, args)
            outputs.append(out)
            if rc != 0:
                module.fail_json(msg="fdroidcl repo add failed for %s" % name, rc=rc, output=out)
            changed = True
            current[key] = True
            enabled = True

        if not enabled:
            rc, out = run_fdroidcl(module, ["repo", "enable", name])
            outputs.append(out)
            if rc != 0:
                module.fail_json(msg="fdroidcl repo enable failed for %s" % name, rc=rc, output=out)
            changed = True
            current[key] = True

    return changed, outputs, ensured


def ensure_setups(module, setups, apply_setups, check_mode):
    """Create/update fdroidcl setups and optionally apply them.

    fdroidcl setups have no reliable read interface, so create/add-repo/add-app
    run unconditionally (idempotent server-side) and only `apply` reports change.
    """
    outputs = []
    changed = False

    for setup in setups:
        name = setup.get("name")
        if not name:
            module.fail_json(msg="each setup requires 'name'")
        if check_mode:
            changed = changed or bool(apply_setups)
            continue

        rc, out = run_fdroidcl(module, ["setup", "new", name])
        outputs.append(out)  # rc!=0 = exists; both fine

        for repo in setup.get("repos") or []:
            rc, out = run_fdroidcl(module, ["setup", "add-repo", name, repo])
            outputs.append(out)
        for app in setup.get("apps") or []:
            rc, out = run_fdroidcl(module, ["setup", "add-app", name, app])
            outputs.append(out)

        if apply_setups:
            rc, out = run_fdroidcl(module, ["setup", "apply", name])
            outputs.append(out)
            if rc != 0:
                module.fail_json(msg="fdroidcl setup apply failed for %s" % name, rc=rc, output=out)
            changed = True

    return changed, outputs


def main():
    module = AnsibleModule(
        argument_spec=dict(
            repos=dict(type="list", elements="dict", default=[]),
            setups=dict(type="list", elements="dict", default=[]),
            apply_setups=dict(type="bool", default=True),
            device=dict(type="str", default="localhost:5555"),
            update_index=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    desired = module.params["repos"]
    setups = module.params["setups"]
    device = resolve_adb(module.params["device"], module.run_command)
    outputs = []
    changed = False
    ensured = []

    if desired or setups:
        rc, out = run_cmd(module, ["adb", "connect", device])
        outputs.append("adb connect %s: rc=%s" % (device, rc))
        rc, out = run_cmd(module, ["adb", "-s", device, "shell", "true"])
        if rc != 0:
            module.fail_json(
                msg="adb device %s not reachable (fdroidcl needs a connected device for index sync)" % device,
                adb_output=out,
            )

        rc, repo_list_out = run_fdroidcl(module, ["repo"])
        if rc != 0:
            module.fail_json(msg="fdroidcl repo failed", rc=rc, output=repo_list_out)
        current = parse_current_repos(repo_list_out)

        repo_changed, repo_out, ensured = ensure_repos(module, desired, current, module.check_mode)
        outputs.extend(repo_out)
        changed = changed or repo_changed

        if repo_changed and module.params["update_index"] and not module.check_mode:
            rc, out = run_fdroidcl(module, ["update"])
            outputs.append(out)
            if rc != 0:
                module.warn("fdroidcl update failed after repo change: %s" % out)

        if setups:
            setups_changed, setup_out = ensure_setups(module, setups, module.params["apply_setups"], module.check_mode)
            outputs.extend(setup_out)
            changed = changed or setups_changed

    module.exit_json(
        changed=changed,
        repos=ensured,
        fdroidcl_output=outputs,
        device_resolved=device,
    )


if __name__ == "__main__":
    main()
