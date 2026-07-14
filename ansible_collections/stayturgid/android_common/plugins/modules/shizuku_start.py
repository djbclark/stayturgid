#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: shizuku_start
short_description: Start Shizuku on a device via ADB and apply fleet profile
description:
  - Starts the Shizuku daemon on an Android device over ADB.
  - First tries C(HEADLESS_START) broadcast (works when Shizuku has been paired).
  - Falls back to direct C(libshizuku.so) native launch (first-time, no pairing).
  - Applies the fleet profile (TCP mode, start-on-boot, watchdog) after start.
  - Verifies the daemon is running and port 5555 is reachable.
  - Idempotent: skips when Shizuku is already running with port 5555 open.
options:
  device:
    description: ADB device serial.
    type: str
    required: true
  shizuku_pkg:
    description: Shizuku package name.
    type: str
    default: moe.shizuku.privileged.api
  connect:
    description: Run C(adb connect) before other operations.
    type: bool
    default: true
  fleet_profile:
    description: Fleet profile JSON to apply after start.
    type: dict
  start_timeout:
    description: Maximum seconds to wait for Shizuku to come up.
    type: int
    default: 15
"""

EXAMPLES = r"""
- name: Start Shizuku and apply fleet profile
  stayturgid.android_common.shizuku_start:
    device: "{{ adb_target }}"
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when Shizuku was started.
  type: bool
shizuku:
  description: Final Shizuku state (up / down / already_up).
  type: str
start_method:
  description: How Shizuku was started (headless / native / already_up).
  type: str
port5555:
  description: Whether port 5555 is open after start.
  type: str
"""

import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
)

SHIZUKU_PKG = "moe.shizuku.privileged.api"
HEADLESS_START = "moe.shizuku.privileged.api.HEADLESS_START"
HEADLESS_STATUS = "moe.shizuku.privileged.api.HEADLESS_STATUS"
APPLY_FLEET = "moe.shizuku.privileged.api.APPLY_FLEET_PROFILE"
FLEET_ACTIVITY = "moe.shizuku.privileged.api/moe.shizuku.manager.fleet.FleetProfileActivity"
FLEET_PROFILE_PATH = "/data/local/tmp/shizuku-fleet.json"

DEFAULT_FLEET_PROFILE = {
    "mode": "adb",
    "start_on_boot": True,
    "tcp_mode": True,
    "tcp_port": 5555,
    "watchdog": True,
}


def shizuku_installed(run_command, device, pkg=SHIZUKU_PKG):
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % pkg)
    if rc != 0:
        return False
    return "package:" in normalize_adb_output(out)


def shizuku_running(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "am broadcast -a %s 2>/dev/null" % HEADLESS_STATUS)
    text = normalize_adb_output(out)
    if rc == 0 and "result=1" in text:
        return True
    rc, out, _err = adb_shell(run_command, device, "pgrep -f '[s]hizuku_server' >/dev/null && echo up")
    return rc == 0 and "up" in normalize_adb_output(out)


def port5555_open(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "grep -q ':15B3' /proc/net/tcp && echo open || echo closed")
    return rc == 0 and "open" in normalize_adb_output(out)


def send_headless_start(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "am broadcast -a %s" % HEADLESS_START)
    normalize_adb_output(out)
    return rc == 0


def resolve_libdir(run_command, device, pkg=SHIZUKU_PKG):
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % pkg)
    if rc != 0:
        return None
    for line in normalize_adb_output(out).splitlines():
        line = line.strip()
        if line.startswith("package:"):
            apk = line.split(":", 1)[1]
            return apk.rsplit("/", 1)[0] + "/lib/arm64"
    return None


def start_native(run_command, device, libdir, pkg=SHIZUKU_PKG):
    cmd = (
        "test -x %s/libshizuku.so && "
        "LD_LIBRARY_PATH=%s %s/libshizuku.so || "
        "sh /storage/emulated/0/Android/data/%s/start.sh"
    ) % (libdir, libdir, libdir, pkg)
    return adb_shell(run_command, device, cmd)


def push_fleet_profile(module, device, profile):
    import json
    import os
    import tempfile

    content = json.dumps(profile, separators=(",", ":"))
    tmp = tempfile.NamedTemporaryFile("w", dir=module.tmpdir, suffix=".json", delete=False)
    try:
        tmp.write(content)
        tmp.close()
        rc, _out, err = module.run_command(["adb", "-s", device, "push", tmp.name, FLEET_PROFILE_PATH])
        if rc != 0:
            return False, "push fleet profile failed: %s" % normalize_adb_output(err)
    finally:
        os.unlink(tmp.name)
    rc, _out, err = adb_shell(module.run_command, device, "chmod 644 %s" % FLEET_PROFILE_PATH)
    if rc != 0:
        return False, "chmod fleet profile failed"
    return True, "ok"


def apply_fleet_profile(run_command, device):
    rc, _out, _err = adb_shell(
        run_command,
        device,
        "am start --user 0 -a %s -e profile_path %s -e silent true -n %s"
        % (APPLY_FLEET, FLEET_PROFILE_PATH, FLEET_ACTIVITY),
    )
    return rc == 0


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            shizuku_pkg=dict(type="str", default=SHIZUKU_PKG),
            connect=dict(type="bool", default=True),
            fleet_profile=dict(type="dict"),
            start_timeout=dict(type="int", default=15),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    pkg = module.params["shizuku_pkg"]

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    if module.check_mode:
        running = shizuku_running(module.run_command, device)
        if running:
            module.exit_json(changed=False, shizuku="already_up", start_method="already_up", port5555="unknown")
        module.exit_json(changed=True, shizuku="down", start_method="would_start", port5555="unknown")

    if not shizuku_installed(module.run_command, device, pkg):
        module.fail_json(msg="Shizuku (%s) is not installed on %s" % (pkg, device))

    running = shizuku_running(module.run_command, device)
    port_open = port5555_open(module.run_command, device) if running else False

    if running and port_open:
        module.exit_json(changed=False, shizuku="already_up", start_method="already_up", port5555="open")

    if running and not port_open:
        module.exit_json(changed=False, shizuku="up_no_port", start_method="already_up", port5555="closed")

    start_method = "none"

    send_headless_start(module.run_command, device)
    time.sleep(3)
    if shizuku_running(module.run_command, device):
        start_method = "headless"
    else:
        libdir = resolve_libdir(module.run_command, device, pkg)
        if libdir:
            rc, _out, _err = start_native(module.run_command, device, libdir, pkg)
            time.sleep(2)
            if shizuku_running(module.run_command, device):
                start_method = "native"
            else:
                module.fail_json(msg="Shizuku failed to start via both HEADLESS_START and native launch")

    push_fleet_profile(module, device, module.params["fleet_profile"] or DEFAULT_FLEET_PROFILE)
    apply_fleet_profile(module.run_command, device)
    time.sleep(1)
    send_headless_start(module.run_command, device)

    deadline = time.time() + module.params["start_timeout"]
    while time.time() < deadline:
        if shizuku_running(module.run_command, device) and port5555_open(module.run_command, device):
            break
        time.sleep(1)

    final_running = shizuku_running(module.run_command, device)
    final_port = "open" if port5555_open(module.run_command, device) else "closed"

    if final_running and final_port == "open":
        module.exit_json(changed=True, shizuku="up", start_method=start_method, port5555=final_port)
    elif final_running:
        module.warn("Shizuku is running but port 5555 is closed — fleet profile may need a second apply")
        module.exit_json(changed=True, shizuku="up_no_port", start_method=start_method, port5555="closed")
    else:
        module.fail_json(msg="Shizuku failed to come up within %ds timeout" % module.params["start_timeout"])


if __name__ == "__main__":
    main()
