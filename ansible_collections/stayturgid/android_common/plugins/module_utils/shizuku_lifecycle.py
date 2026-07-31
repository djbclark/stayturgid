# -*- coding: utf-8 -*-
"""Shared Shizuku process-lifecycle helpers.

Extracted from shizuku_start.py so shizuku_grant.py can force a restart
after changing a permission grant (stayturgid#<TBD>): ShizukuConfigManager's
in-memory authorization state is only reconciled from the real Android
permission grant (`pm grant`/`pm revoke`) at server *startup* -- a `pm
grant` alone has no effect on an already-running server, and neither does
hand-editing shizuku.json. Only a restart (or the very first start) makes a
new grant/revoke actually take effect.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_shell,
    normalize_adb_output,
)

SHIZUKU_PKG = "moe.shizuku.privileged.api"
HEADLESS_STATUS = "moe.shizuku.privileged.api.HEADLESS_STATUS"


def shizuku_running(run_command, device):
    """True if the Shizuku server process is currently alive on device."""
    rc, out, _err = adb_shell(run_command, device, "am broadcast -a %s 2>/dev/null" % HEADLESS_STATUS)
    text = normalize_adb_output(out)
    if rc == 0 and "result=1" in text:
        return True
    rc, out, _err = adb_shell(run_command, device, "pgrep -f '[s]hizuku_server' >/dev/null && echo up")
    return rc == 0 and "up" in normalize_adb_output(out)


def resolve_libdir(run_command, device, pkg=SHIZUKU_PKG):
    """Resolve the installed Shizuku APK's native lib dir via `pm path`.

    Dynamic resolution (rather than a fixed pre-extracted starter binary
    path) so this stays correct across Shizuku app updates.
    """
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % pkg)
    if rc != 0:
        return None
    for line in normalize_adb_output(out).splitlines():
        line = line.strip()
        if line.startswith("package:"):
            apk = line.split(":", 1)[1]
            return apk.rsplit("/", 1)[0] + "/lib/arm64"
    return None


def start_native(run_command, device, libdir, pkg=SHIZUKU_PKG):
    """Launch (or relaunch) shizuku_server via the APK's own libshizuku.so.

    libshizuku.so kills any existing shizuku_server before starting a new
    one, so this doubles as the "force restart" primitive -- no separate
    kill step is needed.
    """
    cmd = (
        "test -x %s/libshizuku.so && "
        "LD_LIBRARY_PATH=%s %s/libshizuku.so || "
        "sh /storage/emulated/0/Android/data/%s/start.sh"
    ) % (libdir, libdir, libdir, pkg)
    return adb_shell(run_command, device, cmd)


def restart_shizuku_if_running(run_command, device, shizuku_pkg=SHIZUKU_PKG):
    """Force a Shizuku server restart, but only if one is already running.

    A permission change made while Shizuku isn't running needs no action --
    the next natural start already reconciles from the real `pm grant`
    state (see ShizukuConfigManager's constructor). Restarting a server
    that isn't up would be a no-op start, not a meaningful restart, so this
    is intentionally conditional.

    Returns (attempted, ok): ``attempted`` is False when Shizuku wasn't
    running (nothing to do); ``ok`` is only meaningful when ``attempted``
    is True.
    """
    if not shizuku_running(run_command, device):
        return False, True
    libdir = resolve_libdir(run_command, device, shizuku_pkg)
    if not libdir:
        return True, False
    rc, _out, _err = start_native(run_command, device, libdir, shizuku_pkg)
    return True, rc == 0
