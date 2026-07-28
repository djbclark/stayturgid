# -*- coding: utf-8 -*-
"""Lookup plugin: preferred fdroidrepos:// activity component."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: fdroid_client
short_description: Preferred F-Droid GUI client activity for fdroidrepos intents
description:
  - Returns the activity component for the highest-preference installed client
    (Neo Store > Droid-ify > F-Droid), defaulting to Neo Store.
options:
  _terms:
    description: ADB device target.
    required: true
"""

EXAMPLES = r"""
- ansible.builtin.set_fact:
    _fdroid_component: "{{ lookup('stayturgid.android_common.fdroid_client', adb_target) }}"
"""

import subprocess

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
        fdroid_components_for_device,
        preferred_fdroid_component,
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
    from adb_packages import fdroid_components_for_device, preferred_fdroid_component
    from adb_timeout import DEFAULT_FAST_TIMEOUT, run_command_with_timeout


def _raw_run_command(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        raise AnsibleError("fdroid_client lookup failed to run %s: %s" % (cmd, exc))


def _run_command(cmd):
    """Query-class adb call from the control node (#59) — wrap with the
    shared coreutils timeout(1) helper so a wedged shell/adbd can't hang
    this lookup forever, even if this function is ever called directly
    rather than via preferred_fdroid_component()/fdroid_components_for_device().
    No get_bin_path_fn override here (defaults to None, same as every
    adb_shell.py caller upstream of this function) — that's deliberate: it
    makes this call share the same process-wide resolved-binary cache as
    the outer run_command_with_timeout() wrap adb_connect()/adb_shell()
    already apply, so the double-wrap guard reliably recognizes an
    already-wrapped incoming cmd and no-ops instead of prefixing `timeout`
    a second time. A get_bin_path_fn that resolves differently (e.g.
    shutil.which, which searches $PATH rather than the fixed candidate
    list) could pick a different absolute path than the outer wrap and
    defeat that guard."""
    return run_command_with_timeout(_raw_run_command, cmd, timeout=DEFAULT_FAST_TIMEOUT)


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        if not terms:
            raise AnsibleError("fdroid_client lookup requires a device term")
        device = self._templar.template(terms[0])
        wantlist = kwargs.get("wantlist", False)
        if wantlist:
            return fdroid_components_for_device(_run_command, str(device))
        return [preferred_fdroid_component(_run_command, str(device))]
