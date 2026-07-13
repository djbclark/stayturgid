# -*- coding: utf-8 -*-
"""Lookup plugin: resolve fleet alias to ADB target on the control node."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: adb_device
short_description: Resolve stayturgid fleet alias to ADB serial or host:port
description:
  - Reads C(~/.config/stayturgid/devices.conf) (or C(STAYTURGID_DEVICES_CONF)).
  - Prefers USB serial when the device is connected.
  - Otherwise tries LAN then Tailscale C(ip:5555), running C(adb connect) when needed.
  - Scans connected devices by C(ro.serialno) when inventory IPs drift.
  - Unknown aliases pass through unchanged (raw serial or host:port).
options:
  _terms:
    description: Device alias or raw ADB target.
    required: true
"""

EXAMPLES = r"""
- name: Grant Shizuku using resolved ADB target
  ansible.builtin.command:
    argv: [python3, grant.py, "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"]
  delegate_to: localhost
"""

import subprocess

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)

display = Display()


def _run_command(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        raise AnsibleError("adb_device lookup failed to run %s: %s" % (cmd, exc))


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        ret = []
        for term in terms:
            alias = self._templar.template(term)
            ret.append(resolve_adb(str(alias), run_command=_run_command))
        return ret
