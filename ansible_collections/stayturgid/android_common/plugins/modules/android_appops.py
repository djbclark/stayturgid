#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_appops
short_description: Idempotent Android appops and runtime permission grants via adb
description:
  - Sets C(cmd appops) modes and grants runtime permissions with C(pm grant) over adb.
  - Skips packages that are not installed when C(skip_missing_packages=true).
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  appops:
    description: List of appops to ensure.
    type: list
    elements: dict
    suboptions:
      package:
        type: str
        required: true
      op:
        type: str
        required: true
      mode:
        type: str
        default: allow
        choices: [allow, ignore, deny, default]
  permissions:
    description: Runtime permissions to grant with C(pm grant).
    type: list
    elements: dict
    suboptions:
      package:
        type: str
        required: true
      permission:
        type: str
        required: true
  skip_missing_packages:
    description: Skip grants when the package is not installed on the device.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Grant Termux overlay and notification permissions (privileged shell)
  stayturgid.android_common.android_appops:
    device: localhost:5555
    appops:
      - package: com.termux.api
        op: WRITE_SETTINGS
        mode: allow
      - package: com.termux
        op: SYSTEM_ALERT_WINDOW
        mode: allow
    permissions:
      - package: com.termux
        permission: android.permission.POST_NOTIFICATIONS
"""

RETURN = r"""
changed:
  description: Whether any grant or appops change was applied.
  type: bool
results:
  description: Per-item outcomes.
  type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    appops_get,
    appops_set,
    normalize_adb_output,
    package_installed,
    parse_appops_mode,
    pm_grant,
)


def ensure_appop(run_command, device, package, op, mode, check_mode):
    rc, out, _err = appops_get(run_command, device, package, op)
    current = parse_appops_mode(out if rc == 0 else "")
    if current == mode:
        return False, "already"
    if check_mode:
        return True, "would_set"
    rc, _out, err = appops_set(run_command, device, package, op, mode)
    if rc == 0:
        return True, "set"
    return False, normalize_adb_output(err) or "failed"


def ensure_permission(run_command, device, package, permission, check_mode):
    if check_mode:
        return True, "would_grant"
    changed, status = pm_grant(run_command, device, package, permission)
    return changed, status


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            appops=dict(
                type="list",
                elements="dict",
                options=dict(
                    package=dict(type="str", required=True),
                    op=dict(type="str", required=True),
                    mode=dict(
                        type="str",
                        default="allow",
                        choices=["allow", "ignore", "deny", "default"],
                    ),
                ),
            ),
            permissions=dict(
                type="list",
                elements="dict",
                options=dict(
                    package=dict(type="str", required=True),
                    permission=dict(type="str", required=True),
                ),
            ),
            skip_missing_packages=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    appops = module.params["appops"] or []
    permissions = module.params["permissions"] or []
    results = []
    changed = False

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    for item in appops:
        pkg = item["package"]
        if module.params["skip_missing_packages"] and not package_installed(
            module.run_command, device, pkg
        ):
            results.append(
                dict(kind="appops", package=pkg, op=item["op"], status="skipped")
            )
            continue
        item_changed, status = ensure_appop(
            module.run_command,
            device,
            pkg,
            item["op"],
            item["mode"],
            module.check_mode,
        )
        changed = changed or item_changed
        results.append(
            dict(kind="appops", package=pkg, op=item["op"], status=status)
        )

    for item in permissions:
        pkg = item["package"]
        perm = item["permission"]
        if module.params["skip_missing_packages"] and not package_installed(
            module.run_command, device, pkg
        ):
            results.append(
                dict(kind="permission", package=pkg, permission=perm, status="skipped")
            )
            continue
        item_changed, status = ensure_permission(
            module.run_command, device, pkg, perm, module.check_mode
        )
        changed = changed or item_changed
        results.append(
            dict(kind="permission", package=pkg, permission=perm, status=status)
        )

    module.exit_json(changed=changed, results=results)


if __name__ == "__main__":
    main()
