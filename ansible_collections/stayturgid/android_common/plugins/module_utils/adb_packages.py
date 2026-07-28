# -*- coding: utf-8 -*-
"""List installed Android packages via adb."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
        adb_connect,
        adb_shell,
        normalize_adb_output,
    )
except ImportError:
    import os
    import sys

    _mod_dir = os.path.dirname(os.path.abspath(__file__))
    if _mod_dir not in sys.path:
        sys.path.insert(0, _mod_dir)
    from adb_shell import (
        adb_connect,
        adb_shell,
        normalize_adb_output,
    )

# Preference order for fdroidrepos:// handler resolution.
FDROID_CLIENTS = (
    ("com.machiav3lli.fdroid", "com.machiav3lli.fdroid/.NeoActivity"),
    ("com.looker.droidify", "com.looker.droidify/.MainActivity"),
    (
        "org.fdroid.fdroid",
        "org.fdroid.fdroid/org.fdroid.fdroid.views.main.MainActivity",
    ),
)


def list_packages(run_command, device, connect=True):
    if connect:
        adb_connect(run_command, device)
    rc, out, _err = adb_shell(run_command, device, "pm list packages --user 0")
    if rc != 0:
        return []
    pkgs = []
    for line in normalize_adb_output(out).splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line.split(":", 1)[1])
    return pkgs


def packages_matching(run_command, device, pattern=None, connect=True):
    pkgs = list_packages(run_command, device, connect=connect)
    if not pattern:
        return pkgs
    rx = re.compile(pattern)
    return [p for p in pkgs if rx.search(p)]


def package_installed_on_device(run_command, device, package, connect=True):
    return package in list_packages(run_command, device, connect=connect)


def preferred_fdroid_component(run_command, device, connect=True):
    """First installed F-Droid GUI client component, or Neo default."""
    installed = set(list_packages(run_command, device, connect=connect))
    for pkg, component in FDROID_CLIENTS:
        if pkg in installed:
            return component
    return FDROID_CLIENTS[0][1]


def fdroid_components_for_device(run_command, device, connect=True):
    """All components for installed F-Droid clients (preference order)."""
    installed = set(list_packages(run_command, device, connect=connect))
    return [comp for pkg, comp in FDROID_CLIENTS if pkg in installed]
