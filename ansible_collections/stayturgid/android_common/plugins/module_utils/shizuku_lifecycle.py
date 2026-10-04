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

import re

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_shell,
    normalize_adb_output,
)

SHIZUKU_PKG = "moe.shizuku.privileged.api"
HEADLESS_STATUS = "moe.shizuku.privileged.api.HEADLESS_STATUS"

# ShizukuTendCF keeps a durable marker once its own "Allow USB debugging?"
# dialog goes unanswered. While it is set a plain HEADLESS_START is withheld
# (result code 4, data AUTH_UNANSWERED) and HEADLESS_STATUS's data ends with
# " AUTH_UNANSWERED". `--ez force true` clears it and may raise a new dialog,
# so it is for an operator at the phone and nothing here sends it. Builds that
# predate the marker never report either.
AUTH_UNANSWERED = "AUTH_UNANSWERED"
RESTART_WITHHELD = "withheld"
SHIZUKU_START_WITHHELD_MSG = (
    "shizuku start withheld: ADB authorisation dialog unanswered; operator: tap Attempt now on the phone"
)


def status_auth_unanswered(status_text):
    """True when a HEADLESS_STATUS reply carries the unanswered-dialog marker.

    Only the data/extras say so: HEADLESS_STATUS's result code is the server
    state's ordinal, and 4 there means CRASHED.
    """
    return AUTH_UNANSWERED in (status_text or "")


def start_withheld(start_text):
    """True when a HEADLESS_START reply says the start was withheld."""
    text = start_text or ""
    return AUTH_UNANSWERED in text or re.search(r"\bresult=4\b", text) is not None


def shizuku_status_text(run_command, device):
    """The HEADLESS_STATUS reply, or "" when adb failed."""
    rc, out, _err = adb_shell(
        run_command, device, "am broadcast -a %s -p %s 2>/dev/null" % (HEADLESS_STATUS, SHIZUKU_PKG)
    )
    return normalize_adb_output(out) if rc == 0 else ""


def shizuku_running(run_command, device, status_text=None):
    """True if the Shizuku server process is currently alive on device."""
    text = shizuku_status_text(run_command, device) if status_text is None else status_text
    if "result=1" in text:
        return True
    rc, out, _err = adb_shell(run_command, device, "pgrep -f '[s]hizuku_(plus_)?server' >/dev/null && echo up")
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

    The starter never goes through HEADLESS_START, so it would ignore an
    unanswered authorisation dialog; while one is, the running server is left
    alone and ``(False, RESTART_WITHHELD)`` comes back.

    Returns (attempted, ok): ``attempted`` is False when Shizuku wasn't
    running (nothing to do); ``ok`` is only meaningful when ``attempted``
    is True.
    """
    status = shizuku_status_text(run_command, device)
    if not shizuku_running(run_command, device, status):
        return False, True
    if status_auth_unanswered(status):
        return False, RESTART_WITHHELD
    libdir = resolve_libdir(run_command, device, shizuku_pkg)
    if not libdir:
        return True, False
    rc, _out, _err = start_native(run_command, device, libdir, shizuku_pkg)
    return True, rc == 0
