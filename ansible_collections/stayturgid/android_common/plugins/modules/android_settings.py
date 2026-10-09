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
  lockdown_management_host:
    description:
      - Address the control node manages this device through (normally C(ansible_host)).
      - Used by the always-on VPN lockdown interlock, see I(notes).
    type: str
  lockdown_management_port:
    description: TCP port on I(lockdown_management_host) the interlock must reach (Termux sshd by default).
    type: int
    default: 8022
notes:
  - "Lockdown interlock (stayturgid#289): a request for C(secure/always_on_vpn_lockdown=1)
    is honoured only when (1) a tunN/tailscale interface on the device holds an IPv4 in
    100.64.0.0/10, so Tailscale is logged in and connected, (2) I(lockdown_management_host)
    is that same tailnet address, so Ansible already reaches the device over the VPN, and
    (3) a TCP connect from the control node to that host and I(lockdown_management_port)
    succeeds. Otherwise lockdown is written as C(0), a warning names the failed check,
    and C(lockdown_interlock.blocked) is true. Blocking traffic outside a VPN that is not
    up would sever ADB-over-TCP and Termux SSH, and recovery is physical."
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
lockdown_interlock:
  description: Present when lockdown=1 was requested. C(blocked), C(reason), C(device_tailnet_ip).
  type: dict
"""

import socket

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    device_tailnet_ipv4,
    is_tailnet_ipv4,
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


LOCKDOWN_NAMESPACE = "secure"
LOCKDOWN_KEY = "always_on_vpn_lockdown"
MANAGEMENT_CONNECT_TIMEOUT = 5


def tcp_reachable(host, port, timeout=MANAGEMENT_CONNECT_TIMEOUT):
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
    except (OSError, ValueError):
        return False
    sock.close()
    return True


def lockdown_interlock(run_command, device, management_host, management_port, reachable=tcp_reachable):
    """Return (allowed, reason, device_tailnet_ip) for enabling VPN lockdown (#289)."""
    tailnet_ip = device_tailnet_ipv4(run_command, device)
    if not tailnet_ip:
        return (
            False,
            "Tailscale is not logged in and connected on the device (no 100.64.0.0/10 address on a tun interface)",
            None,
        )
    if not management_host:
        return False, "no management host given, so the management path cannot be verified", tailnet_ip
    if not is_tailnet_ipv4(management_host):
        return (
            False,
            "the control node manages this device through %s, which is not a tailnet address; lockdown would cut that path"
            % management_host,
            tailnet_ip,
        )
    if management_host != tailnet_ip:
        return (
            False,
            "management host %s is not the device's tailnet address %s" % (management_host, tailnet_ip),
            tailnet_ip,
        )
    if not reachable(management_host, management_port):
        return (
            False,
            "management path %s:%s is not reachable from the control node over the tailnet"
            % (management_host, management_port),
            tailnet_ip,
        )
    return True, "verified", tailnet_ip


def apply_lockdown_interlock(module, device, settings):
    """Rewrite a lockdown=1 request to 0 unless the interlock passes. Returns the interlock report or None."""
    wants_lockdown = [
        item
        for item in settings
        if item["namespace"] == LOCKDOWN_NAMESPACE and item["key"] == LOCKDOWN_KEY and item["value"] == "1"
    ]
    if not wants_lockdown:
        return None
    allowed, reason, tailnet_ip = lockdown_interlock(
        module.run_command,
        device,
        module.params.get("lockdown_management_host"),
        module.params.get("lockdown_management_port"),
        reachable=tcp_reachable,
    )
    if not allowed:
        for item in wants_lockdown:
            item["value"] = "0"
        module.warn(
            "always_on_vpn_lockdown=1 refused, left at 0 (stayturgid#289 interlock): %s. "
            "Log in to Tailscale on the device and manage it through its tailnet address first." % reason
        )
    return dict(blocked=not allowed, reason=reason, device_tailnet_ip=tailnet_ip)


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
            lockdown_management_host=dict(type="str"),
            lockdown_management_port=dict(type="int", default=8022),
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

    if require_package and not package_installed(module.run_command, device, require_package):
        skipped = True
        module.exit_json(changed=False, skipped=True, results=[])

    interlock = apply_lockdown_interlock(module, device, settings)

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

    extra = {} if interlock is None else dict(lockdown_interlock=interlock)
    module.exit_json(changed=changed, skipped=skipped, results=results, **extra)


if __name__ == "__main__":
    main()
