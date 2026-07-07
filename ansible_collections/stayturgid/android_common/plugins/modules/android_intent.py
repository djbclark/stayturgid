#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_intent
short_description: Fire an Android intent via adb shell am start
description:
  - Thin wrapper over C(adb shell am start) with structured parameters.
  - When C(component) is set and the explicit start fails (activity renamed
    across app versions), optionally falls back to an implicit intent so the
    system chooser can still resolve it.
  - Intents are fire-and-forget; the module reports C(changed=true) whenever
    an intent was sent (set C(changed=false) in the task via C(changed_when)
    if you treat it as a query).
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  action:
    description: Intent action (e.g. C(android.intent.action.VIEW)).
    type: str
    default: android.intent.action.VIEW
  data:
    description: Intent data URI (e.g. C(fdroidrepos://...), C(market://...)).
    type: str
  mime_type:
    description: Intent MIME type (C(-t)).
    type: str
  component:
    description: Explicit component (C(-n pkg/Activity)).
    type: str
  fallback_implicit:
    description: Retry without C(component) when the explicit start fails.
    type: bool
    default: true
  extras:
    description: String extras (C(--es key value)).
    type: dict
    default: {}
"""

EXAMPLES = r"""
- name: Push F-Droid repo to Neo Store
  stayturgid.android_common.android_intent:
    device: "{{ adb_target }}"
    data: "fdroidrepos://apt.izzysoft.de/fdroid/repo?fingerprint=3BF0..."
    component: com.machiav3lli.fdroid/.NeoActivity
  delegate_to: localhost
  changed_when: false
"""

RETURN = r"""
used_component:
  description: Whether the explicit component start succeeded (false = implicit fallback).
  type: bool
output:
  description: am start output.
  type: str
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
)


def build_am_start(action, data, mime_type, component, extras):
    parts = ["am", "start", "-a", action]
    if data:
        parts += ["-d", "'%s'" % data]
    if mime_type:
        parts += ["-t", "'%s'" % mime_type]
    if component:
        parts += ["-n", "'%s'" % component]
    for key, value in sorted((extras or {}).items()):
        parts += ["--es", "'%s'" % key, "'%s'" % value]
    return " ".join(parts)


def am_start_failed(rc, output):
    text = (output or "").lower()
    return rc != 0 or "error" in text or "exception" in text or "does not exist" in text


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            action=dict(type="str", default="android.intent.action.VIEW"),
            data=dict(type="str"),
            mime_type=dict(type="str"),
            component=dict(type="str"),
            fallback_implicit=dict(type="bool", default=True),
            extras=dict(type="dict", default={}),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]

    if module.check_mode:
        module.exit_json(changed=True, used_component=bool(module.params["component"]))

    if module.params["connect"]:
        adb_connect(module.run_command, device)

    cmd = build_am_start(
        module.params["action"],
        module.params["data"],
        module.params["mime_type"],
        module.params["component"],
        module.params["extras"],
    )
    rc, out, err = adb_shell(module.run_command, device, cmd)
    output = normalize_adb_output(out + "\n" + err)
    used_component = bool(module.params["component"])

    if (
        am_start_failed(rc, output)
        and module.params["component"]
        and module.params["fallback_implicit"]
    ):
        cmd = build_am_start(
            module.params["action"],
            module.params["data"],
            module.params["mime_type"],
            None,
            module.params["extras"],
        )
        rc, out, err = adb_shell(module.run_command, device, cmd)
        output = normalize_adb_output(out + "\n" + err)
        used_component = False

    if am_start_failed(rc, output):
        module.fail_json(msg="am start failed: %s" % output)

    module.exit_json(changed=True, used_component=used_component, output=output)


if __name__ == "__main__":
    main()
