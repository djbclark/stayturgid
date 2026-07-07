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

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
    fdroid_components_for_device,
    preferred_fdroid_component,
)


def _run_command(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        raise AnsibleError("fdroid_client lookup failed to run %s: %s" % (cmd, exc))


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        if not terms:
            raise AnsibleError("fdroid_client lookup requires a device term")
        device = self._templar.template(terms[0], disable_lookups=False)
        wantlist = kwargs.get("wantlist", False)
        if wantlist:
            return fdroid_components_for_device(_run_command, str(device))
        return [preferred_fdroid_component(_run_command, str(device))]
