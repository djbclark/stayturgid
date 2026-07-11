#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_sshd
short_description: Manage Termux sshd_config and detached restart
description:
  - >-
    Ensures sshd_config options and a detached sshd restart on the Termux
    prefix. SSH public keys are managed separately with
    C(ansible.posix.authorized_key) in the termux_userland role.
  - Config changes are validated with C(sshd -t) before being written.
  - >-
    The restart is detached (delayed C(pkill) + relaunch) so it does not kill
    the SSH session Ansible is using.
options:
  config:
    description: >-
      sshd_config options to ensure, e.g. C({PerSourcePenalties: "no"}).
    type: dict
    default: {}
  restart_on_change:
    description: Restart sshd (detached) when sshd_config changed.
    type: bool
    default: true
  ensure_running:
    description: >-
      If true, remove the runsv ``down`` file so the sshd service can start.
      A stale ``down`` file (e.g. left by manual troubleshooting) silently
      prevents sshd from launching after reboot.
    type: bool
    default: true
  termux_prefix:
    description: Termux prefix.
    type: str
    default: /data/data/com.termux/files/usr
"""

EXAMPLES = r"""
- name: Lockout prevention for OpenSSH 10.x on Termux
  stayturgid.termux.termux_sshd:
    config:
      PerSourcePenalties: "no"

- name: Ensure sshd is not disabled by a stale down file
  stayturgid.termux.termux_sshd:
    ensure_running: true
"""

RETURN = r"""
changed:
  description: True when sshd_config changed or the down file was removed.
  type: bool
config_changed:
  type: bool
  description: sshd_config was modified (triggers restart when enabled).
down_removed:
  type: bool
  description: >-
    True when a stale runsv ``down`` file was removed, allowing the sshd
    service to start on next boot.
"""

import os
import re

from ansible.module_utils.basic import AnsibleModule


def apply_config(text, options):
    """lineinfile-style keyed replace for each sshd_config option."""
    lines = text.splitlines()
    for key, value in options.items():
        wanted = "%s %s" % (key, value)
        pattern = re.compile(r"^#?\s*%s\b" % re.escape(key))
        replaced = False
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = wanted
                replaced = True
                break
        if not replaced:
            lines.append(wanted)
    return "\n".join(lines) + "\n"


def read_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            config=dict(type="dict", default={}),
            restart_on_change=dict(type="bool", default=True),
            ensure_running=dict(type="bool", default=True),
            termux_prefix=dict(type="str", default="/data/data/com.termux/files/usr"),
        ),
        supports_check_mode=True,
    )

    prefix = module.params["termux_prefix"]
    sshd_config = os.path.join(prefix, "etc", "ssh", "sshd_config")
    service_dir = os.path.join(prefix, "var", "service", "sshd")
    config_changed = False
    down_removed = False

    # --- ensure_running: remove stale down file ---
    if module.params["ensure_running"]:
        down_path = os.path.join(service_dir, "down")
        if os.path.isfile(down_path):
            if not module.check_mode:
                os.unlink(down_path)
            down_removed = True

    if module.params["config"]:
        current = read_file(sshd_config)
        new_text = apply_config(current, module.params["config"])
        if new_text != current:
            config_changed = True
            if not module.check_mode:
                tmp = sshd_config + ".ansible-tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(new_text)
                sshd_bin = os.path.join(prefix, "bin", "sshd")
                rc, _out, err = module.run_command([sshd_bin, "-t", "-f", tmp])
                if rc != 0:
                    os.unlink(tmp)
                    module.fail_json(msg="sshd -t rejected new config: %s" % err.strip())
                os.replace(tmp, sshd_config)

    if config_changed and module.params["restart_on_change"] and not module.check_mode:
        # Detached: an inline restart would kill the SSH session Ansible uses.
        bash = os.path.join(prefix, "bin", "bash")
        module.run_command(
            [bash, "-c", "nohup bash -c 'sleep 5; pkill -x sshd; sleep 1; sshd' >/dev/null 2>&1 &"]
        )

    module.exit_json(
        changed=config_changed or down_removed,
        config_changed=config_changed,
        down_removed=down_removed,
    )


if __name__ == "__main__":
    main()
