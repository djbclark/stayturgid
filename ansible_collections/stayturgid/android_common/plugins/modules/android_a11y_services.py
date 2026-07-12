#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_a11y_services
short_description: Backup or merge-restore enabled_accessibility_services via adb
description:
  - Merge-only writes for C(settings put secure enabled_accessibility_services).
  - Uses fleet profiles under C(repo_root)/control/lib/a11y_profiles.json and backups
    in C(repo_root)/control/lib/a11y_backups/.
options:
  device:
    description: ADB serial or C(host:5555).
    type: str
    required: true
  alias:
    description: Fleet host alias for profile lookup (e.g. C(s24)).
    type: str
    required: true
  repo_root:
    description: stayturgid repository root on the control node.
    type: path
    required: true
  state:
    description: C(backup) snapshots live list; C(present) merge-restore; C(restore) uses C(restore_mode).
    type: str
    default: present
    choices: [backup, present, restore]
  restore_mode:
    description: Source for C(restore) / implied merge for C(present).
    type: str
    default: merge
    choices: [merge, profile, backup]
  connect:
    description: Run C(adb connect) for wireless targets.
    type: bool
    default: true
  ensure_autojs6:
    description: Include AutoJs6 accessibility service in merge/present.
    type: bool
    default: true
  push_device_backup:
    description: When backing up, also push snapshot to device C(/sdcard/stayturgid/state/).
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Merge-restore accessibility services for s24
  stayturgid.android_common.android_a11y_services:
    device: "{{ lookup('stayturgid.android_common.adb_device', 's24') }}"
    alias: s24
    repo_root: "{{ stayturgid_repo_root }}"
    state: present
  delegate_to: localhost
"""

RETURN = r"""
changed:
  type: bool
services_before:
  type: str
services_after:
  type: str
services_count:
  type: int
"""

import os
import subprocess
import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell
from ansible_collections.stayturgid.android_common.plugins.module_utils import (
    a11y_services_util as a11y,
)

DEVICE_BACKUP_REL = "state/a11y_services_backup.txt"
SD_ROOT = "/sdcard/stayturgid"


def settings_get(run_command, device):
    rc, out, _err = adb_shell.adb_shell(
        run_command,
        device,
        "settings get secure enabled_accessibility_services",
    )
    if rc != 0:
        return ""
    return a11y.normalize_value(out)


def settings_put(run_command, device, value, check_mode=False):
    current = settings_get(run_command, device)
    target = a11y.normalize_value(value)
    if current == target:
        return False, current, target
    if check_mode:
        return True, current, target
    adb_shell.adb_shell(
        run_command,
        device,
        "settings put secure enabled_accessibility_services %s" % target,
    )
    adb_shell.adb_shell(
        run_command,
        device,
        "settings put secure accessibility_enabled 1",
    )
    # Android 13+ shows a confirmation dialog when accessibility services
    # are modified via settings put.  Dismiss it if it appeared.
    adb_shell.adb_shell(
        run_command,
        device,
        "input keyevent KEYCODE_BACK 2>/dev/null; true",
    )
    return True, current, target


def push_device_backup(run_command, device, repo_root, alias, value, check_mode=False):
    if check_mode:
        return
    backups_dir = os.path.join(repo_root, "control", "lib", "a11y_backups")
    tmp = a11y.backup_file_for(".device_push_%s" % alias, backups_dir)
    a11y.write_backup_file(tmp, value)
    adb_shell.adb_shell(run_command, device, "mkdir -p %s/state" % SD_ROOT)
    subprocess.run(
        ["adb", "-s", device, "push", tmp, "%s/%s" % (SD_ROOT, DEVICE_BACKUP_REL)],
        check=False,
    )
    try:
        os.unlink(tmp)
    except OSError:
        pass


def resolve_target(alias, repo_root, live, backup, mode, ensure_autojs6):
    profiles_path = os.path.join(repo_root, "control", "lib", "a11y_profiles.json")
    backups_dir = os.path.join(repo_root, "control", "lib", "a11y_backups")
    if mode == "profile":
        return a11y.join_services(a11y.profile_services(alias, profiles_path))
    if mode == "backup":
        return backup or a11y.join_services(a11y.profile_services(alias, profiles_path))
    return a11y.desired_services(alias, backup or live, profiles_path, ensure_autojs6)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            alias=dict(type="str", required=True),
            repo_root=dict(type="path", required=True),
            state=dict(
                type="str",
                default="present",
                choices=["backup", "present", "restore"],
            ),
            restore_mode=dict(
                type="str",
                default="merge",
                choices=["merge", "profile", "backup"],
            ),
            connect=dict(type="bool", default=True),
            ensure_autojs6=dict(type="bool", default=True),
            push_device_backup=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    alias = module.params["alias"]
    repo_root = os.path.expanduser(module.params["repo_root"])
    backups_dir = os.path.join(repo_root, "control", "lib", "a11y_backups")
    backup_path = a11y.backup_file_for(alias, backups_dir)

    if module.params["connect"]:
        adb_shell.adb_connect(module.run_command, device)

    live = settings_get(module.run_command, device)
    backup = a11y.read_backup_file(backup_path)
    state = module.params["state"]

    if state == "backup":
        if module.check_mode:
            module.exit_json(
                changed=bool(live),
                services_before=live,
                services_after=live,
                services_count=len(a11y.parse_services(live)),
            )
        a11y.write_backup_file(backup_path, live)
        if module.params["push_device_backup"]:
            push_device_backup(
                module.run_command, device, repo_root, alias, live, check_mode=False
            )
        module.exit_json(
            changed=True,
            services_before=live,
            services_after=live,
            services_count=len(a11y.parse_services(live)),
        )

    mode = module.params["restore_mode"] if state == "restore" else "merge"
    target = resolve_target(
        alias,
        repo_root,
        live,
        backup,
        mode,
        module.params["ensure_autojs6"],
    )
    if not target:
        module.fail_json(msg="no restore target for alias %s" % alias)

    changed, before, after = settings_put(
        module.run_command, device, target, check_mode=module.check_mode
    )
    if not module.check_mode and changed:
        time.sleep(0.5)
        after = settings_get(module.run_command, device)

    module.exit_json(
        changed=changed,
        services_before=before,
        services_after=after,
        services_count=len(a11y.parse_services(after)),
        lost=a11y.services_lost(before, after),
    )


if __name__ == "__main__":
    main()
