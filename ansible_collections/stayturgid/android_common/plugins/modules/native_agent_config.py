#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: native_agent_config
short_description: Reconcile stayturgid native-agent peer configuration over ADB
description:
  - Writes the complete peer target assignment consumed by the native agent.
  - Compares parsed JSON, so formatting differences do not cause false changes.
  - Supports check mode and fails closed when the desired file cannot be installed.
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  package:
    description: Installed native-agent package id.
    type: str
    default: org.stayturgid.agent
  targets:
    description: Complete desired list of peer ADB targets.
    type: list
    elements: str
    required: true
  shizuku_package:
    description: Shizuku package to start on each peer target.
    type: str
    default: moe.shizuku.privileged.api
  connect:
    description: Run C(adb connect) before other operations.
    type: bool
    default: true
"""

RETURN = r"""
changed:
  description: Whether the peer configuration changed.
  type: bool
path:
  description: Reconciled device path.
  type: str
"""

import json
import os
import shlex
import tempfile

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
    package_installed,
)


def desired_config(targets, shizuku_package):
    return {
        "shizuku_pkg": shizuku_package,
        "targets": targets,
    }


def parse_config(text):
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def external_config_path(package):
    return "/sdcard/Android/data/%s/files/peer.json" % package


def install_config(module, device, package, content):
    destination = external_config_path(package)
    staging = "/data/local/tmp/stayturgid-peer.json"
    tmp = tempfile.NamedTemporaryFile("w", dir=module.tmpdir, delete=False)
    try:
        tmp.write(content)
        tmp.close()
        rc, _out, err = module.run_command(["adb", "-s", device, "push", tmp.name, staging])
        if rc != 0:
            module.fail_json(msg="native-agent config staging failed: %s" % normalize_adb_output(err))
    finally:
        os.unlink(tmp.name)

    directory = destination.rsplit("/", 1)[0]
    rc, _out, err = adb_shell(
        module.run_command,
        device,
        "mkdir -p %s && cp %s %s && rm -f %s"
        % tuple(shlex.quote(path) for path in (directory, staging, destination, staging)),
    )
    if rc != 0:
        module.fail_json(msg="native-agent config install failed at %s: %s" % (destination, normalize_adb_output(err)))
    return destination


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", default="org.stayturgid.agent"),
            targets=dict(type="list", elements="str", required=True),
            shizuku_package=dict(type="str", default="moe.shizuku.privileged.api"),
            connect=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    package = module.params["package"]
    targets = module.params["targets"]
    destination = external_config_path(package)

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)
    if not package_installed(module.run_command, device, package):
        module.fail_json(msg="%s is not installed on %s" % (package, device))

    wanted = desired_config(targets, module.params["shizuku_package"])
    rc, out, _err = adb_shell(module.run_command, device, "cat %s" % shlex.quote(destination))
    current = parse_config(normalize_adb_output(out)) if rc == 0 else None
    if current == wanted:
        module.exit_json(changed=False, path=destination)
    if module.check_mode:
        module.exit_json(changed=True, path=destination)

    content = json.dumps(wanted, indent=2, sort_keys=True) + "\n"
    install_config(module, device, package, content)

    rc, out, err = adb_shell(module.run_command, device, "cat %s" % shlex.quote(destination))
    actual = parse_config(normalize_adb_output(out)) if rc == 0 else None
    if actual != wanted:
        module.fail_json(
            msg="native-agent config verification failed at %s: %s" % (destination, normalize_adb_output(err or out))
        )
    module.exit_json(changed=True, path=destination)


if __name__ == "__main__":
    main()
