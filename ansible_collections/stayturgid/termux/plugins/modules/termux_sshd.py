#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_sshd
short_description: Manage Termux sshd authorized_keys, config, and restart in one step
description:
  - Ensures authorized_keys entries, sshd_config options, and a detached sshd
    restart on the Termux prefix — the combined equivalent of
    C(ansible.posix.authorized_key) + C(lineinfile) + a restart handler.
  - Config changes are validated with C(sshd -t) before being written.
  - The restart is detached (delayed C(pkill) + relaunch) so it does not kill
    the SSH session Ansible is using.
options:
  keys:
    description: SSH public key lines to ensure in authorized_keys.
    type: list
    elements: str
    default: []
  exclusive:
    description: Remove keys not listed in C(keys).
    type: bool
    default: false
  authorized_keys_path:
    description: Path to authorized_keys (default Termux home).
    type: path
  config:
    description: sshd_config options to ensure, e.g. C({PerSourcePenalties: "no"}).
    type: dict
    default: {}
  restart_on_change:
    description: Restart sshd (detached) when sshd_config changed.
    type: bool
    default: true
  termux_prefix:
    description: Termux prefix.
    type: str
    default: /data/data/com.termux/files/usr
"""

EXAMPLES = r"""
- name: Operator keys + lockout prevention
  stayturgid.termux.termux_sshd:
    keys: "{{ my_pubkey_lines }}"
    config:
      PerSourcePenalties: "no"
"""

RETURN = r"""
changed:
  description: True when keys or config changed.
  type: bool
keys_changed:
  type: bool
  description: authorized_keys was modified.
config_changed:
  type: bool
  description: sshd_config was modified (triggers restart when enabled).
"""

import os
import re

from ansible.module_utils.basic import AnsibleModule


def key_identity(line):
    """Public key line -> (type, blob) for duplicate detection."""
    parts = line.split()
    if len(parts) >= 2:
        return (parts[0], parts[1])
    return (line.strip(), "")


def merge_keys(existing_lines, wanted, exclusive):
    wanted = [k.strip() for k in wanted if k.strip()]
    wanted_ids = {key_identity(k) for k in wanted}
    if exclusive:
        return list(wanted)
    result = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            result.append(stripped)
            continue
        if key_identity(stripped) in wanted_ids:
            continue  # replaced by the wanted version (comment may differ)
        result.append(stripped)
    result.extend(wanted)
    return result


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
            keys=dict(type="list", elements="str", default=[], no_log=False),
            exclusive=dict(type="bool", default=False),
            authorized_keys_path=dict(type="path"),
            config=dict(type="dict", default={}),
            restart_on_change=dict(type="bool", default=True),
            termux_prefix=dict(type="str", default="/data/data/com.termux/files/usr"),
        ),
        supports_check_mode=True,
    )

    prefix = module.params["termux_prefix"]
    home = os.path.expanduser("~")
    ak_path = module.params["authorized_keys_path"] or os.path.join(
        home, ".ssh", "authorized_keys"
    )
    sshd_config = os.path.join(prefix, "etc", "ssh", "sshd_config")
    keys_changed = False
    config_changed = False

    if module.params["keys"] or module.params["exclusive"]:
        current = read_file(ak_path)
        merged = merge_keys(
            current.splitlines(), module.params["keys"], module.params["exclusive"]
        )
        new_text = "\n".join(merged) + "\n" if merged else ""
        if new_text != current:
            keys_changed = True
            if not module.check_mode:
                ssh_dir = os.path.dirname(ak_path)
                if not os.path.isdir(ssh_dir):
                    os.makedirs(ssh_dir, mode=0o700)
                with open(ak_path, "w", encoding="utf-8") as fh:
                    fh.write(new_text)
                os.chmod(ak_path, 0o600)

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
        changed=keys_changed or config_changed,
        keys_changed=keys_changed,
        config_changed=config_changed,
    )


if __name__ == "__main__":
    main()
