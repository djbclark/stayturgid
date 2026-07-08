#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: stayturgid_repair_check
short_description: Run stayturgid-repair and parse the STATUS line
description:
  - Executes the on-device repair script over the Termux SSH connection and
    parses its C(STATUS …) output into structured fields.
  - Mirrors the device-tier C(parse_heal) rule: C(healthy=true) when
    C(port=open) or C(port=skip) (Fire OS without localhost loopback).
options:
  repair_script:
    description: Path to stayturgid-repair on the device.
    type: path
    default: ~/.stayturgid/bin/stayturgid-repair.sh
  termux_prefix:
    description: Termux prefix (bash executable lives here).
    type: str
    default: /data/data/com.termux/files/usr
  fail_on_unhealthy:
    description: >-
      When true, fail the task if the script reports an unhealthy STATUS
      (C(rc=1), e.g. C(port=CLOSED_NO_SHELL)). When false, return
      C(healthy=false) but exit successfully — matches the previous shell
      task's C(failed_when) behaviour.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Verify repair layer after deploy
  stayturgid.termux.stayturgid_repair_check:
    repair_script: "{{ termux_home }}/.stayturgid/bin/stayturgid-repair.sh"
    termux_prefix: "{{ termux_prefix }}"
  register: repair

- name: Show STATUS
  ansible.builtin.debug:
    var: repair.status_line
"""

RETURN = r"""
changed:
  description: Always false — repair check is read-only from Ansible's view.
  type: bool
healthy:
  description: True when port=open or port=skip.
  type: bool
status_line:
  description: Raw STATUS line from repair stdout.
  type: str
port:
  type: str
shizuku:
  type: str
sshd:
  type: str
a11y:
  type: str
shell:
  type: str
rc:
  description: Repair script exit code.
  type: int
skipped:
  description: True in check mode when the script was not run.
  type: bool
"""

import os
import re

from ansible.module_utils.basic import AnsibleModule

STATUS_RE = re.compile(
    r"^STATUS port=(?P<port>\S+) shizuku=(?P<shizuku>\S+) sshd=(?P<sshd>\S+)"
    r"(?: a11y=(?P<a11y>\S+))? shell=(?P<shell>\S+)"
)


def find_status_line(stdout):
    """Return the last STATUS line from repair stdout, or ""."""
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("STATUS "):
            return stripped
    return ""


def parse_status_line(line):
    """Parse a STATUS line into a dict; None when the line does not match."""
    match = STATUS_RE.match(line.strip())
    if not match:
        return None
    return match.groupdict()


def is_healthy(parsed):
    """Match device_tier.parse_heal — open port or Fire OS skip."""
    if not parsed:
        return False
    port = parsed.get("port") or ""
    return port in ("open", "skip")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            repair_script=dict(type="path"),
            termux_prefix=dict(
                type="str", default="/data/data/com.termux/files/usr"
            ),
            fail_on_unhealthy=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )

    prefix = module.params["termux_prefix"]
    home = os.path.expanduser("~")
    script = module.params["repair_script"] or os.path.join(
        home, ".stayturgid", "bin", "stayturgid-repair.sh"
    )
    bash = os.path.join(prefix, "bin", "bash")

    if module.check_mode:
        module.exit_json(
            changed=False,
            healthy=False,
            skipped=True,
            status_line="",
            rc=0,
        )

    if not os.path.isfile(script):
        module.fail_json(msg="repair script not found: %s" % script)

    rc, stdout, stderr = module.run_command([bash, script])
    status_line = find_status_line(stdout)
    parsed = parse_status_line(status_line) if status_line else None
    healthy = is_healthy(parsed)

    if rc not in (0, 1):
        module.fail_json(
            msg="repair script failed (rc=%d): %s" % (rc, stderr.strip() or stdout.strip()),
            rc=rc,
            status_line=status_line,
            healthy=healthy,
        )

    if module.params["fail_on_unhealthy"] and not healthy:
        module.fail_json(
            msg="repair STATUS unhealthy: %s" % (status_line or "no STATUS line"),
            rc=rc,
            status_line=status_line,
            healthy=False,
            **(parsed or {}),
        )

    result = dict(
        changed=False,
        healthy=healthy,
        skipped=False,
        status_line=status_line,
        rc=rc,
    )
    if parsed:
        result.update(parsed)
    module.exit_json(**result)


if __name__ == "__main__":
    main()
