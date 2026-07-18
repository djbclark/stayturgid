#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fdroid_apps
short_description: Ensure F-Droid apps are installed via fdroidcl
description:
  - Runs C(fdroidcl install) for each app id on the control node with
    C(ANDROID_SERIAL) set to the adb target.
  - Idempotent when packages are already installed (skips fdroidcl unless
    C(force=true) on an entry).
  - Does not install Neo Store — use the C(obtainium_apps) role first.
options:
  apps:
    description: F-Droid apps to ensure.
    type: list
    elements: dict
    required: true
    suboptions:
      id:
        type: str
        required: true
        description: F-Droid application id (package name).
      force:
        type: bool
        default: false
        description: Run fdroidcl even when the package is already installed.
  device:
    description: ADB target or fleet alias (resolved on control node).
    type: str
    default: localhost:5555
author:
  - stayturgid project
"""

EXAMPLES = r"""
- name: Install F-Droid apps
  stayturgid.fdroid.fdroid_apps:
    device: stock-android-device
    apps:
      - id: org.breezyweather
  delegate_to: localhost
"""

RETURN = r"""
changed:
  type: bool
installed:
  type: list
  elements: str
skipped:
  type: list
  elements: str
device_resolved:
  type: str
output:
  type: list
  elements: str
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)
from ansible_collections.stayturgid.fdroid.plugins.module_utils.fdroidcl_install import (
    install_fdroid_app,
)


def _app_id(entry):
    app_id = entry.get("id")
    if not app_id:
        raise ValueError("each app entry requires id")
    return app_id


def main():
    module = AnsibleModule(
        argument_spec=dict(
            apps=dict(type="list", elements="dict", required=True),
            device=dict(type="str", default="localhost:5555"),
        ),
        supports_check_mode=True,
    )

    device = resolve_adb(module.params["device"], module.run_command)
    apps = module.params["apps"] or []

    installed = []
    skipped = []
    output = []
    changed = False

    for entry in apps:
        package = _app_id(entry)
        force = bool(entry.get("force", False))
        try:
            app_changed, detail = install_fdroid_app(
                module.run_command,
                device,
                package,
                force=force,
                check_mode=module.check_mode,
            )
        except ValueError as exc:
            module.fail_json(msg=str(exc))
        except RuntimeError as exc:
            module.fail_json(msg=str(exc))

        if app_changed:
            changed = True
            installed.append(package)
            if detail and detail != "would install":
                output.append(detail)
        else:
            skipped.append(package)

    module.exit_json(
        changed=changed,
        installed=installed,
        skipped=skipped,
        device_resolved=device,
        output=output,
    )


if __name__ == "__main__":
    main()
