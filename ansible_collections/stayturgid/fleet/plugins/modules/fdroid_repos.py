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
    description: F-Droid repos to ensure present and enabled in fdroidcl.
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
  stayturgid.fleet.fdroid_repos:
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

import os
import re

from ansible.module_utils.basic import AnsibleModule

DEVICES_CONF = os.path.expanduser("~/.config/stayturgid/devices.conf")


def device_row(alias):
    try:
        with open(DEVICES_CONF) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0] == alias:
                    return tuple((parts[1:] + ["-", "-", "-"])[:3])
    except OSError:
        pass
    return None


def resolve_device(alias, module):
    """Fleet alias -> USB serial when plugged in, else tailscale host:5555."""
    row = device_row(alias)
    if row:
        usb, ts_ip, _lan = row
        if usb != "-":
            rc, out, _err = module.run_command(["adb", "devices"])
            if rc == 0 and ("%s\tdevice" % usb) in (out or ""):
                return usb
        if ts_ip and ts_ip != "-":
            return "%s:5555" % ts_ip
    return alias


def normalize_url(url):
    return (url or "").strip().rstrip("/")


def normalize_fingerprint(fp):
    if not fp:
        return ""
    return re.sub(r"[^0-9A-Fa-f]", "", str(fp)).upper()


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
        if not name or not address:
            module.fail_json(msg="each repo requires 'name' and 'address'")
        key = repo_key(name, address)
        ensured.append({"name": key[0], "address": key[1]})

        present = repo_present(current, name, address)
        enabled = repo_enabled(current, name, address)

        if check_mode:
            if not present or not enabled:
                changed = True
            continue

        if not present:
            args = ["repo", "add", name, normalize_url(address)]
            fp = normalize_fingerprint(spec.get("fingerprint"))
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


def main():
    module = AnsibleModule(
        argument_spec=dict(
            repos=dict(type="list", elements="dict", default=[]),
            device=dict(type="str", default="localhost:5555"),
            update_index=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    desired = module.params["repos"]
    device = resolve_device(module.params["device"], module)
    outputs = []
    changed = False
    ensured = []

    if desired:
        rc, out = run_cmd(module, ["adb", "connect", device])
        outputs.append("adb connect %s: rc=%s" % (device, rc))
        rc, out = run_cmd(module, ["adb", "-s", device, "shell", "true"])
        if rc != 0:
            module.fail_json(
                msg="adb device %s not reachable (fdroidcl needs a connected device for index sync)"
                % device,
                adb_output=out,
            )

        rc, repo_list_out = run_fdroidcl(module, ["repo"])
        if rc != 0:
            module.fail_json(msg="fdroidcl repo failed", rc=rc, output=repo_list_out)
        current = parse_current_repos(repo_list_out)

        repo_changed, repo_out, ensured = ensure_repos(
            module, desired, current, module.check_mode
        )
        outputs.extend(repo_out)
        changed = changed or repo_changed

        if repo_changed and module.params["update_index"] and not module.check_mode:
            rc, out = run_fdroidcl(module, ["update"])
            outputs.append(out)
            if rc != 0:
                module.warn("fdroidcl update failed after repo change: %s" % out)

    module.exit_json(
        changed=changed,
        repos=ensured,
        fdroidcl_output=outputs,
        device_resolved=device,
    )


if __name__ == "__main__":
    main()
