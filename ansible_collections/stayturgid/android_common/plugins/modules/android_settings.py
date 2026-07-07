#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_settings
short_description: Idempotent Android settings put via adb
description:
  - Ensures C(settings put) values in the C(secure), C(global), or C(system) namespaces.
  - Optionally skips all changes when a required package is not installed.
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  settings:
    description: Settings to ensure.
    type: list
    elements: dict
    required: true
    suboptions:
      namespace:
        type: str
        required: true
        choices: [secure, global, system]
      key:
        type: str
        required: true
      value:
        type: str
        required: true
  require_package:
    description: When set, skip all changes if this package is not installed.
    type: str
"""

EXAMPLES = r"""
- name: Tailscale always-on VPN
  stayturgid.android_common.android_settings:
    device: "{{ adb_target }}"
    require_package: com.tailscale.ipn
    settings:
      - namespace: secure
        key: always_on_vpn_app
        value: com.tailscale.ipn
      - namespace: secure
        key: always_on_vpn_lockdown
        value: "1"
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: Whether any setting was updated.
  type: bool
skipped:
  description: True when C(require_package) is missing from the device.
  type: bool
results:
  description: Per-setting outcomes.
  type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    normalize_adb_output,
    package_installed,
    settings_get,
    settings_put,
)


def ensure_setting(run_command, device, namespace, key, value, check_mode):
    rc, out, _err = settings_get(run_command, device, namespace, key)
    current = normalize_adb_output(out if rc == 0 else "")
    if current == value:
        return False, "already"
    if check_mode:
        return True, "would_set"
    rc, _out, err = settings_put(run_command, device, namespace, key, value)
    if rc == 0:
        return True, "set"
    return False, normalize_adb_output(err) or "failed"


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            settings=dict(
                type="list",
                elements="dict",
                required=True,
                options=dict(
                    namespace=dict(
                        type="str",
                        required=True,
                        choices=["secure", "global", "system"],
                    ),
                    key=dict(type="str", required=True),
                    value=dict(type="str", required=True),
                ),
            ),
            require_package=dict(type="str"),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    settings = module.params["settings"]
    require_package = module.params["require_package"]
    results = []
    changed = False
    skipped = False

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    if require_package and not package_installed(
        module.run_command, device, require_package
    ):
        skipped = True
        module.exit_json(changed=False, skipped=True, results=[])

    for item in settings:
        item_changed, status = ensure_setting(
            module.run_command,
            device,
            item["namespace"],
            item["key"],
            item["value"],
            module.check_mode,
        )
        changed = changed or item_changed
        results.append(
            dict(
                namespace=item["namespace"],
                key=item["key"],
                value=item["value"],
                status=status,
            )
        )

    module.exit_json(changed=changed, skipped=skipped, results=results)


if __name__ == "__main__":
    main()
