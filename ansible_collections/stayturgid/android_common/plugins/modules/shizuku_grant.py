#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: shizuku_grant
short_description: Grant Shizuku API access to an app via the privileged adb shell
description:
  - Grants C(moe.shizuku.manager.permission.API_V23) with C(pm grant), then forces
    a Shizuku server restart (only if one is already running) so the grant takes
    effect immediately.
  - Runs on the control node against an adb target with a privileged shell
    (Shizuku adbd, uid 2000).
  - >-
    Historically this module also hand-patched Shizuku's C(shizuku.json)
    authorization file directly. That file's per-app C(flags) are only ever a
    cache reconciled from the real C(pm grant)/C(pm revoke) state at Shizuku
    server *startup* (see C(ShizukuConfigManager)'s constructor upstream) --
    editing it directly, or restarting without first fixing the underlying
    C(pm) grant, has no effect on an already-running server. This module no
    longer touches that file at all; C(pm grant) plus a conditional restart is
    both simpler and is the mechanism actually verified to work end-to-end.
options:
  device:
    description: ADB device serial or C(host:5555) target with privileged shell.
    type: str
    required: true
  package:
    description: App package to authorize (e.g. org.stayturgid.agent, com.termux).
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Grant Shizuku to Neo Store
  stayturgid.android_common.shizuku_grant:
    device: "{{ adb_target }}"
    package: com.machiav3lli.fdroid
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when the permission was not already granted (a grant + restart happened).
  type: bool
uid:
  description: Resolved app uid.
  type: str
restarted:
  description: True when a Shizuku server restart was attempted as part of this run.
  type: bool
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    permission_granted,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.shizuku import (
    SHIZUKU_PERMISSION,
    parse_uid,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.shizuku_lifecycle import (
    restart_shizuku_if_running,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    pkg = module.params["package"]

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    rc, _out, _err = adb_shell(module.run_command, device, "true")
    if rc != 0:
        module.fail_json(msg="no adb shell on %s — connect device and ensure Shizuku adbd is up" % device)

    rc, out, _err = adb_shell(module.run_command, device, "pm list packages -U %s" % pkg)
    uid = parse_uid(out if rc == 0 else "")
    if not uid:
        module.fail_json(msg="%s not installed on %s" % (pkg, device))

    already_granted = permission_granted(module.run_command, device, pkg, SHIZUKU_PERMISSION)

    if module.check_mode:
        module.exit_json(changed=not already_granted, uid=uid, restarted=False)

    if already_granted:
        module.exit_json(changed=False, uid=uid, restarted=False)

    rc, _out, err = adb_shell(module.run_command, device, "pm grant %s %s" % (pkg, SHIZUKU_PERMISSION))
    if rc != 0:
        module.fail_json(msg="pm grant %s %s failed: %s" % (pkg, SHIZUKU_PERMISSION, err))

    attempted, restart_ok = restart_shizuku_if_running(module.run_command, device)
    if attempted and not restart_ok:
        module.warn(
            "granted %s but the Shizuku server restart failed — the grant "
            "will only take effect on the next natural restart" % pkg
        )

    module.exit_json(changed=True, uid=uid, restarted=attempted)


if __name__ == "__main__":
    main()
