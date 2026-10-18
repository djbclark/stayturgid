#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_screen_ready
short_description: Wait for an awake, unlocked screen before Termux's first adb connect
description:
  - The first C(adb connect localhost:5555) from a Termux whose adb key is not yet
    authorised raises the "Allow USB debugging?" dialog, and Samsung drops that
    dialog silently on the lock screen (C(startConfirmation: isLockScreenMode)),
    so nobody ever sees it. This module checks C(dumpsys window) isKeyguardShowing
    and C(dumpsys power) mWakefulness over the control node's adb. When the phone
    is asleep or locked it sends one C(hermes-ping) and polls until it is awake and
    unlocked, or fails after C(timeout).
  - With C(only_unless_key_authorized) it does nothing when Termux's own adb key is
    already in adbd's key store (no dialog can be raised then).
  - An unreadable state (adb failure, no dumpsys line) proceeds; the next adb call
    reports the real fault.
  - Runs on the control node; use with C(delegate_to: localhost).
options:
  device:
    description: ADB device serial or C(host:5555) target. Empty skips the check.
    type: str
    required: true
  host:
    description: Fleet host name used in the ping text.
    type: str
  purpose:
    description: Words completing "unlock <host> for ..." in the ping.
    type: str
    default: deploy-termux
  timeout:
    description: Seconds to wait for the unlock.
    type: int
    default: 600
  poll_interval:
    description: Seconds between polls.
    type: int
    default: 10
  only_unless_key_authorized:
    description: Skip the check when Termux's adb key is already authorised.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Wait for an unlocked screen before Termux's first adb connect
  stayturgid.termux.termux_screen_ready:
    device: "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
    host: "{{ inventory_hostname }}"
  delegate_to: localhost
"""

RETURN = r"""
checked:
  description: False when the check was skipped (no device, or the key is already authorised).
  type: bool
waited:
  description: True when the phone was locked or asleep and the module waited for it.
  type: bool
key_state:
  description: Termux's adb key state (authorized, unauthorized, no-key, unknown) when it was read.
  type: str
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.termux.plugins.module_utils.termux_run_as import (
    adbkey_state,
    wait_for_unlocked_screen,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            host=dict(type="str"),
            purpose=dict(type="str", default="deploy-termux"),
            timeout=dict(type="int", default=600),
            poll_interval=dict(type="int", default=10),
            only_unless_key_authorized=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )
    device = module.params["device"]
    if not device or module.check_mode:
        module.exit_json(changed=False, checked=False, waited=False, key_state="")

    key_state = ""
    if module.params["only_unless_key_authorized"]:
        key_state = adbkey_state(module.run_command, device)
        if key_state == "authorized":
            module.exit_json(changed=False, checked=False, waited=False, key_state=key_state)

    try:
        waited = wait_for_unlocked_screen(
            module.run_command,
            device,
            host=module.params["host"],
            purpose=module.params["purpose"],
            timeout_s=module.params["timeout"],
            poll_s=module.params["poll_interval"],
        )
    except RuntimeError as exc:
        module.fail_json(msg=str(exc), key_state=key_state)

    module.exit_json(changed=False, checked=True, waited=waited, key_state=key_state)


if __name__ == "__main__":
    main()
