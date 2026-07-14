#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_a11y_services
short_description: Read and report enabled_accessibility_services via adb
description:
  - Detection-only — no automatic writes or merge-repair.
  - Reads current accessibility services list and reports whether AutoJs6 is enabled.
options:
  device:
    description: ADB serial or C(host:5555).
    type: str
    required: true
  connect:
    description: Run C(adb connect) for wireless targets.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Report accessibility services for s24
  stayturgid.android_common.android_a11y_services:
    device: "{{ lookup('stayturgid.android_common.adb_device', 's24') }}"
"""

RETURN = r"""
services:
  type: str
autojs6_present:
  type: bool
services_count:
  type: int
"""


from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils import (
    a11y_services_util as a11y,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell


def settings_get(run_command, device):
    rc, out, _err = adb_shell.adb_shell(
        run_command,
        device,
        "settings get secure enabled_accessibility_services",
    )
    if rc != 0:
        return ""
    return a11y.normalize_value(out)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]

    if module.params["connect"]:
        adb_shell.adb_connect(module.run_command, device)

    live = settings_get(module.run_command, device)
    services = a11y.parse_services(live)
    autojs6_present = a11y.has_autojs6(live)

    module.exit_json(
        services=live,
        autojs6_present=autojs6_present,
        services_count=len(services),
        services_list=services,
    )


if __name__ == "__main__":
    main()
