#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: autojs6_project_deploy
short_description: Deploy the stayturgid AutoJs6 project tree over adb
description:
  - Pushes C(project.json), C(main.js), C(lib/), and C(scripts/) from the repo
    checkout to the device AutoJs6 project path (default C(/sdcard/stayturgid/autojs6)).
  - Wipes remote C(lib/) and C(scripts/) before push to avoid nested C(lib/lib) on
    some adb versions — same behavior as C(control/tools/autojs6/deploy.py).
  - Optionally pushes a rendered C(device.json) to C(/sdcard/stayturgid/state/).
  - Does not install the AutoJs6 APK or nudge the watchdog; use Obtainium and the
    C(autojs6_watchdog) role handlers for that.
options:
  device:
    description: ADB serial or C(host:5555).
    type: str
    required: true
  repo_root:
    description: stayturgid repository root on the control node.
    type: path
    required: true
  target:
    description: Remote AutoJs6 project directory.
    type: path
    default: /sdcard/stayturgid/autojs6
  device_json:
    description: >-
      Local path to a rendered device profile to adb-push (Fire OS / Mac-adb path).
    type: path
  device_json_dest:
    description: Remote path for C(device_json).
    type: path
    default: /sdcard/stayturgid/state/device.json
  connect:
    description: Run C(adb connect) for wireless targets.
    type: bool
    default: true
  deploy_project:
    description: Push the AutoJs6 project tree.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Deploy AutoJs6 project to Fire HD over adb
  stayturgid.android_common.autojs6_project_deploy:
    device: "{{ lookup('stayturgid.android_common.adb_device', 'hd8') }}"
    repo_root: "{{ stayturgid_repo_root }}"
    target: "{{ autojs6_target }}"
    device_json: "/tmp/stayturgid-hd8-device.json"
  delegate_to: localhost
"""

RETURN = r"""
changed:
  type: bool
project_deployed:
  type: bool
device_json_pushed:
  type: bool
target:
  type: str
"""

import os

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell
from ansible_collections.stayturgid.android_common.plugins.module_utils import (
    autojs6_deploy_util as deploy,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            repo_root=dict(type="path", required=True),
            target=dict(type="path", default=deploy.DEFAULT_TARGET),
            device_json=dict(type="path"),
            device_json_dest=dict(type="path", default=deploy.DEFAULT_DEVICE_JSON_DEST),
            connect=dict(type="bool", default=True),
            deploy_project=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    repo_root = os.path.expanduser(module.params["repo_root"])
    target = module.params["target"]
    device_json = module.params["device_json"]
    check_mode = module.check_mode

    if module.params["connect"]:
        adb_shell.adb_connect(module.run_command, device)

    changed = False
    project_deployed = False
    device_json_pushed = False

    if module.params["deploy_project"]:
        ok, msg, proj_changed = deploy.deploy_project(
            module.run_command,
            device,
            repo_root,
            target=target,
            check_mode=check_mode,
        )
        if not ok:
            module.fail_json(msg=msg)
        if proj_changed:
            changed = True
            project_deployed = True

    if device_json:
        ok, msg, json_changed = deploy.push_device_json(
            module.run_command,
            device,
            device_json,
            dest=module.params["device_json_dest"],
            check_mode=check_mode,
        )
        if not ok:
            module.fail_json(msg=msg)
        if json_changed:
            changed = True
            device_json_pushed = True

    module.exit_json(
        changed=changed,
        project_deployed=project_deployed,
        device_json_pushed=device_json_pushed,
        target=target,
    )


if __name__ == "__main__":
    main()
