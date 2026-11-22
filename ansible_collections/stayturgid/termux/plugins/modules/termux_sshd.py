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
  restart_stale:
    description: >-
      Restart the runit-supervised sshd listener when it outlived its binary: its
      C(/proc/PID/exe) is C((deleted)), or it started before C(bin/sshd) or
      C(libexec/sshd-session) last changed. An C(openssh) package upgrade under a
      running listener leaves it resetting every login (C(kex_exchange_identification),
      p7a 2026-11-21). Established sessions survive the restart. A listener not
      under runit is reported, not restarted (the role's runit fix-up retires it).
    type: bool
    default: false
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

- name: Restart a listener left running from a replaced openssh binary
  stayturgid.termux.termux_sshd:
    restart_stale: true
    ensure_running: false
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
stale_listener:
  type: str
  description: >-
    With restart_stale, the listener verdict before any restart: C(fresh),
    C(stale <reason>) or C(unknown <reason>).
stale_restarted:
  type: bool
  description: True when a stale listener was restarted (or would be, in check mode).
"""

import os
import re
import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.plain_run import plain_run_command
from ansible_collections.stayturgid.termux.plugins.module_utils.sshd_stale import (
    parse_verdict,
    restart_script,
    stale_check_script,
)

STALE_POLLS = 15


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


def stale_verdict(module, prefix):
    rc, out, _err = module.run_command([os.path.join(prefix, "bin", "bash"), "-c", stale_check_script(prefix)])
    return parse_verdict(out if rc == 0 else "")


def restart_stale_listener(module, prefix):
    """(listener verdict before, restarted?). Fails the module if the new one is not fresh."""
    verdict = stale_verdict(module, prefix)
    if not verdict.stale:
        return verdict, False
    if not verdict.supervised:
        module.warn(
            "sshd listener is stale (%s) but not supervised by runit: not restarting it here" % verdict.describe()
        )
        return verdict, False
    if module.check_mode:
        return verdict, True
    rc, out, err = module.run_command([os.path.join(prefix, "bin", "bash"), "-c", restart_script(prefix)])
    if rc != 0:
        module.fail_json(
            msg="sv restart sshd failed (rc=%s): %s" % (rc, (err or out).strip()), stale_listener=verdict.describe()
        )
    now = verdict
    for _ in range(STALE_POLLS):
        now = stale_verdict(module, prefix)
        if now.fresh:
            return verdict, True
        time.sleep(1)
    module.fail_json(
        msg="sshd listener is still stale after sv restart (%s)" % now.describe(), stale_listener=verdict.describe()
    )


def main():
    module = AnsibleModule(
        argument_spec=dict(
            config=dict(type="dict", default={}),
            restart_on_change=dict(type="bool", default=True),
            ensure_running=dict(type="bool", default=True),
            restart_stale=dict(type="bool", default=False),
            termux_prefix=dict(type="str", default="/data/data/com.termux/files/usr"),
        ),
        supports_check_mode=True,
    )
    plain_run_command(module)

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
        # Prefer `sv restart` when runsv supervises sshd (runit owns the
        # process; a bare pkill+sshd would race its automatic restart for
        # port 8022), falling back to the historical pkill+start.
        bash = os.path.join(prefix, "bin", "bash")
        svdir = os.path.join(prefix, "var", "service")
        restart = (
            "sleep 5; "
            "if [ -x %(prefix)s/bin/sv ] && SVDIR=%(svdir)s %(prefix)s/bin/sv status sshd >/dev/null 2>&1; "
            "then SVDIR=%(svdir)s %(prefix)s/bin/sv restart sshd; "
            "else pkill -x sshd; sleep 1; sshd; fi"
        ) % {"prefix": prefix, "svdir": svdir}
        module.run_command([bash, "-c", "nohup bash -c '%s' >/dev/null 2>&1 &" % restart])

    stale_listener = ""
    stale_restarted = False
    if module.params["restart_stale"]:
        verdict, stale_restarted = restart_stale_listener(module, prefix)
        stale_listener = verdict.describe()

    module.exit_json(
        changed=config_changed or down_removed or stale_restarted,
        config_changed=config_changed,
        down_removed=down_removed,
        stale_listener=stale_listener,
        stale_restarted=stale_restarted,
    )


if __name__ == "__main__":
    main()
