#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fdroid_install
short_description: Install F-Droid apps on a device via fdroidcl
description:
  - Wraps C(fdroidcl install) with C(ANDROID_SERIAL) set to the adb target.
  - Idempotent when the package is already installed (skips fdroidcl).
options:
  device:
    description: ADB device serial or C(host:5555).
    type: str
    required: true
  package:
    description: F-Droid application id to install.
    type: str
    required: true
  force:
    description: Run fdroidcl even when the package is already on the device.
    type: bool
    default: false
"""

EXAMPLES = r"""
- stayturgid.fdroid.fdroid_install:
    device: "{{ adb_target }}"
    package: org.breezyweather
  delegate_to: localhost
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)
from ansible_collections.stayturgid.fdroid.plugins.module_utils.fdroidcl_install import (
    install_fdroid_app,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", required=True),
            force=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )

    device = resolve_adb(module.params["device"], module.run_command)
    package = module.params["package"]

    try:
        changed, detail = install_fdroid_app(
            module.run_command,
            device,
            package,
            force=module.params["force"],
            check_mode=module.check_mode,
        )
    except RuntimeError as exc:
        module.fail_json(msg=str(exc))

    if changed:
        if detail == "would install":
            module.exit_json(changed=True, reason=detail)
        module.exit_json(changed=True, output=detail)
    module.exit_json(changed=False, reason=detail)


if __name__ == "__main__":
    main()
