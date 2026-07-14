# -*- coding: utf-8 -*-
"""Lookup plugin: list installed packages on an adb device."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: android_packages
short_description: List installed packages on an adb device
description:
  - Runs C(pm list packages --user 0) over adb on the control node.
  - Optional second term is a regex filter on package names.
options:
  _terms:
    description: ADB device target; optional regex as second term.
    required: true
"""

EXAMPLES = r"""
- ansible.builtin.set_fact:
    has_neo: "{{ neo_store_package in lookup('stayturgid.android_common.android_packages', adb_target) }}"

- ansible.builtin.set_fact:
    fdroid_clients: "{{ lookup('stayturgid.android_common.android_packages', adb_target, 'fdroid|droidify') }}"
"""

import subprocess

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
    packages_matching,
)


def _run_command(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        raise AnsibleError("android_packages lookup failed to run %s: %s" % (cmd, exc))


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        if not terms:
            raise AnsibleError("android_packages lookup requires at least a device term")
        device = self._templar.template(terms[0])
        pattern = None
        if len(terms) > 1:
            pattern = self._templar.template(terms[1])
        return packages_matching(_run_command, str(device), pattern=pattern)
