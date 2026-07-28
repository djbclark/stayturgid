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

try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
        resolve_adb,
    )
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_FAST_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_utils = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "module_utils")
    if _mod_utils not in sys.path:
        sys.path.insert(0, _mod_utils)
    from adb_resolve import resolve_adb
    from adb_timeout import DEFAULT_FAST_TIMEOUT, run_command_with_timeout

display = Display()


def _raw_run_command(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        raise AnsibleError("adb_device lookup failed to run %s: %s" % (cmd, exc))


def _run_command(cmd):
    """Query-class adb call from the control node (#59) — wrap with the
    shared coreutils timeout(1) helper so a wedged shell/adbd can't hang
    this lookup forever, even if this function is ever called directly
    rather than via resolve_adb(). No get_bin_path_fn override here
    (defaults to None, same as every adb_resolve.py caller upstream of
    this function) — that's deliberate: it makes this call share the same
    process-wide resolved-binary cache as the outer run_command_with_timeout()
    wrap resolve_adb() already applies, so the double-wrap guard reliably
    recognizes an already-wrapped incoming cmd and no-ops instead of
    prefixing `timeout` a second time. A get_bin_path_fn that resolves
    differently (e.g. shutil.which, which searches $PATH rather than the
    fixed candidate list) could pick a different absolute path than the
    outer wrap and defeat that guard."""
    return run_command_with_timeout(_raw_run_command, cmd, timeout=DEFAULT_FAST_TIMEOUT)


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        ret = []
        for term in terms:
            alias = self._templar.template(term)
            ret.append(resolve_adb(str(alias), run_command=_run_command))
        return ret
