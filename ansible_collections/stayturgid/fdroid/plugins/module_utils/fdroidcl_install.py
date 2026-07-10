# -*- coding: utf-8 -*-
"""Shared fdroidcl install helpers for stayturgid.fdroid modules."""

from __future__ import absolute_import, division, print_function

import os

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
    package_installed_on_device,
)


def fdroidcl_env(device):
    env = os.environ.copy()
    env["ANDROID_SERIAL"] = device
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    return env


def install_fdroid_app(run_command, device, package, force=False, check_mode=False):
    """Install one F-Droid app. Returns (changed, detail). Raises on fdroidcl failure."""
    if not force and package_installed_on_device(run_command, device, package):
        return False, "already installed"

    if check_mode:
        return True, "would install"

    env = fdroidcl_env(device)
    rc, out, err = run_command(
        ["fdroidcl", "install", package],
        environ_update=env,
    )
    combined = ((out or "") + "\n" + (err or "")).strip()
    if rc != 0:
        raise RuntimeError("fdroidcl install %s failed: %s" % (package, combined))
    return True, combined
