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

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
    package_installed_on_device,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)


def _fdroidcl_env(device):
    import os
    env = os.environ.copy()
    env["ANDROID_SERIAL"] = device
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    return env


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

    if not module.params["force"] and package_installed_on_device(
        module.run_command, device, package
    ):
        module.exit_json(changed=False, reason="already installed")

    if module.check_mode:
        module.exit_json(changed=True, reason="would install")

    env = _fdroidcl_env(device)
    rc, out, err = module.run_command(
        ["fdroidcl", "install", package],
        environ_update=env,
    )
    combined = ((out or "") + "\n" + (err or "")).strip()
    if rc != 0:
        module.fail_json(msg="fdroidcl install %s failed: %s" % (package, combined))

    module.exit_json(changed=True, output=combined)


if __name__ == "__main__":
    main()
