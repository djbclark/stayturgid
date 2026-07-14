#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_ssh_bootstrap
short_description: Bootstrap Termux SSH authorized_keys over adb (pre-SSH)
description:
  - Installs control-node SSH public keys into Termux C(~/.ssh/authorized_keys)
    via C(adb push) and C(run-as com.termux) — the pre-SSH path before Ansible
    can connect on port 8022.
  - Optionally installs C(openssh) and starts C(sshd).
  - Requires a debuggable Termux build where C(run-as com.termux) succeeds.
  - Runs on the control node; use with C(delegate_to: localhost).
  - Ongoing key sync after SSH works belongs in C(ansible.posix.authorized_key)
    (see C(termux_userland) role).
options:
  device:
    description: ADB device serial or C(host:5555) wireless target.
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (wireless targets).
    type: bool
    default: true
  keys_dir:
    description: Directory of C(*.pub) files on the control node when
      C(public_key_files) and C(public_keys) are omitted.
    type: path
    default: "~/.ssh"
  public_key_files:
    description: Explicit public key file paths on the control node (overrides C(keys_dir) glob).
    type: list
    elements: path
    default: []
  public_keys:
    description: SSH public key lines to install (overrides file discovery).
    type: list
    elements: str
    default: []
  install_openssh:
    description: Run C(pkg install -y openssh) when the sshd binary is missing.
    type: bool
    default: true
  start_sshd:
    description: Start C(sshd) when it is not already running.
    type: bool
    default: true
  termux_package:
    description: Termux application package name.
    type: str
    default: com.termux
"""

EXAMPLES = r"""
- name: Bootstrap Termux SSH before fleet deploy
  stayturgid.termux.termux_ssh_bootstrap:
    device: "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
    keys_dir: "{{ stayturgid_ssh_keys_dir }}"
  delegate_to: localhost

- name: Bootstrap with explicit key files
  stayturgid.termux.termux_ssh_bootstrap:
    device: RFCX219CHKA
    public_key_files:
      - "{{ lookup('env', 'HOME') }}/.ssh/termux_key.pub"
    connect: false
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when keys, openssh, or sshd state changed.
  type: bool
keys_changed:
  type: bool
openssh_changed:
  type: bool
sshd_changed:
  type: bool
run_as_available:
  type: bool
public_key_count:
  type: int
"""

import os

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.termux.plugins.module_utils.termux_run_as import (
    bootstrap_device,
    discover_pubkey_paths,
    normalize_pubkey_lines,
    read_pubkey_lines,
)


def resolve_pubkey_lines(module):
    if module.params["public_keys"]:
        return normalize_pubkey_lines(module.params["public_keys"])
    paths = module.params["public_key_files"]
    if not paths:
        keys_dir = os.path.expanduser(module.params["keys_dir"])
        paths = discover_pubkey_paths(keys_dir=keys_dir)
    else:
        paths = [os.path.expanduser(p) for p in paths]
    return read_pubkey_lines(paths)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            keys_dir=dict(type="path", default="~/.ssh"),
            public_key_files=dict(type="list", elements="path", default=[]),
            public_keys=dict(type="list", elements="str", default=[], no_log=False),
            install_openssh=dict(type="bool", default=True),
            start_sshd=dict(type="bool", default=True),
            termux_package=dict(type="str", default="com.termux"),
        ),
        supports_check_mode=True,
    )

    try:
        lines = resolve_pubkey_lines(module)
    except OSError as exc:
        module.fail_json(msg="failed to read public keys: %s" % exc)

    if not lines:
        module.fail_json(msg="no public keys found — set public_keys, public_key_files, or add *.pub under keys_dir")

    try:
        result = bootstrap_device(
            module.run_command,
            module.params["device"],
            lines,
            connect=module.params["connect"],
            install_openssh_pkg=module.params["install_openssh"],
            start_sshd_service=module.params["start_sshd"],
            check_mode=module.check_mode,
            termux_pkg=module.params["termux_package"],
        )
    except (RuntimeError, ValueError) as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
