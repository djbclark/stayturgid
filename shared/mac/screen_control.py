#!/usr/bin/env python3
"""Mandatory screen-control session for Mac-side UI automation.

All stayturgid Mac scripts that send input events (tap, swipe, keyevent) must
run inside ScreenControlSession. The session:

  1. Clears PiP / floating overlays that can steal taps (dumpsys + dismiss).
  2. Requests consent on-device (agent-presence request-screen).
  3. Turns on accessibility display inversion (Mac adb — authoritative).
  4. Starts the on-device presence indicator (torch, notification via SSH).
  5. Refuses further input if inversion is off (fail closed).
  6. Cleans up on exit (inversion off, presence off).

Raw `adb shell input …` outside this wrapper can still bypass the policy;
project scripts must not do that. Set STAYTURGID_SKIP_PRESENCE=1 only for
local debugging.
"""
from __future__ import print_function

import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402
import ui_clearance as uc  # noqa: E402

INPUT_PREFIXES = ("input",)
INVERSION_KEY = "accessibility_display_inversion_enabled"
ADB_KEYBOARD = "com.github.uiautomator/.AdbKeyboard"
# Fleet layout deploys presence scripts under ~/.stayturgid/bin/ (not ~/).
PRESENCE_SCRIPT = "~/.stayturgid/bin/agent-presence.sh"
PRESENCE_SCRIPT_LEGACY = "~/agent-presence.sh"


class ScreenControlError(RuntimeError):
    pass


def is_input_command(args):
    """True when adb shell args issue touch/key events."""
    if not args:
        return False
    cmd = args[0]
    if cmd != "input":
        return False
    if len(args) < 2:
        return True
    # uiautomator dump is not input; input text/tap/swipe/keyevent are.
    return args[1] in ("tap", "swipe", "draganddrop", "text", "keyevent", "roll")


def _run(args, **kw):
    try:
        return subprocess.run(args, capture_output=True, text=True, **kw)
    except (OSError, subprocess.TimeoutExpired):
        return None


def mac_adb_shell(serial, *args, timeout=30):
    r = _run(["adb", "-s", serial, "shell"] + list(args), timeout=timeout)
    if r is None:
        return 127, ""
    return r.returncode, r.stdout.replace("\r", "")


def inversion_enabled(serial):
    rc, out = mac_adb_shell(serial, "settings", "get", "secure", INVERSION_KEY)
    if rc != 0:
        return False
    return out.strip() == "1"


def set_inversion(serial, enabled):
    state = "1" if enabled else "0"
    rc, _out = mac_adb_shell(
        serial, "settings", "put", "secure", INVERSION_KEY, state
    )
    return rc == 0 and inversion_enabled(serial) == enabled


def get_default_ime(serial):
    rc, out = mac_adb_shell(serial, "settings", "get", "secure", "default_input_method")
    if rc != 0:
        return None
    ime = out.strip()
    return ime if ime and ime != "null" else None


def set_default_ime(serial, ime):
    if not ime or ime == "null":
        return False
    mac_adb_shell(serial, "ime", "enable", ime)
    rc, _out = mac_adb_shell(
        serial, "settings", "put", "secure", "default_input_method", ime
    )
    return rc == 0 and get_default_ime(serial) == ime


def restore_default_ime(serial, saved_ime):
    """Switch back from automation keyboards (uiautomator2 AdbKeyboard)."""
    if not saved_ime:
        return True
    cur = get_default_ime(serial)
    if cur == saved_ime:
        return True
    if cur != ADB_KEYBOARD and cur:
        return True
    return set_default_ime(serial, saved_ime)


def ssh_presence(host, action, label, agent):
    host = dev.resolve_ssh_host(host) or host
    if not host:
        return 127, "no ssh host"
    # Prefer single-root deploy path; fall back to legacy ~/ shim if present.
    remote = (
        "if [ -x %s ]; then P=%s; elif [ -x %s ]; then P=%s; else exit 127; fi; "
        '"$P" %s %s %s'
        % (
            PRESENCE_SCRIPT,
            PRESENCE_SCRIPT,
            PRESENCE_SCRIPT_LEGACY,
            PRESENCE_SCRIPT_LEGACY,
            action,
            _shell_quote(label),
            _shell_quote(agent),
        )
    )
    # request-screen uses termux-dialog; on Fire OS that can hang past the
    # on-device timeout — keep Mac SSH timeout tight and report distinctly.
    # on/off: Fire torch/notification used to blow 30s; presence.py now skips
    # torch when STAYTURGID_NO_LOCAL_ADB=1, but keep a little headroom.
    if action == "request-screen":
        limit = 25
    elif action in ("on", "off"):
        limit = 45
    else:
        limit = 30
    try:
        r = subprocess.run(
            ["ssh"] + dev.SSH_OPTS + [host, remote],
            capture_output=True,
            text=True,
            timeout=limit,
        )
    except subprocess.TimeoutExpired:
        return 124, "ssh presence timed out after %ss (action=%s)" % (limit, action)
    except OSError as e:
        return 127, str(e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _shell_quote(text):
    return "'" + str(text).replace("'", "'\"'\"'") + "'"


def guarded_adb_shell(serial, active, *args, timeout=30):
    """adb shell wrapper that blocks input unless inversion is on."""
    if active and is_input_command(args) and not inversion_enabled(serial):
        raise ScreenControlError(
            "refusing adb input on %s: accessibility display inversion is off "
            "(screen-control session required)" % serial
        )
    return mac_adb_shell(serial, *args, timeout=timeout)


class ScreenControlSession(object):
    """Context manager: consent + inverted screen for UI automation."""

    def __init__(self, host, label=None, agent=None, skip_request=False):
        self.host = host
        self.serial = dev.resolve_adb(host)
        self.label = label or host
        self.agent = agent or os.environ.get("STAYTURGID_AGENT", "Auto")
        self.skip_request = skip_request
        self.active = False
        self._skip = os.environ.get("STAYTURGID_SKIP_PRESENCE") == "1"
        self._saved_ime = None

    def __enter__(self):
        if self._skip:
            sys.stderr.write(
                "WARN: STAYTURGID_SKIP_PRESENCE=1 — input not gated by inversion\n"
            )
            self.active = True
            return self

        _run(["adb", "connect", self.serial], timeout=15)
        _run(["adb", "-s", self.serial, "wait-for-device"], timeout=30)
        cleared = uc.clear_ui_obstructions(self.serial, mac_adb_shell)
        if cleared:
            print("Cleared UI obstructions on %s: %s" % (self.host, ", ".join(cleared)))
        self._saved_ime = get_default_ime(self.serial)

        if not self.skip_request:
            rc, out = ssh_presence(self.host, "request-screen", self.label, self.agent)
            if rc == 75:
                raise ScreenControlError("screen control denied on %s" % self.host)
            # rc 127 = presence script missing — fail closed (do not skip consent).
            if rc != 0:
                raise ScreenControlError(
                    "request-screen failed on %s (rc=%s): %s" % (self.host, rc, out.strip())
                )

        if not set_inversion(self.serial, True):
            raise ScreenControlError(
                "failed to enable display inversion on %s" % self.serial
            )

        rc, out = ssh_presence(self.host, "on", self.label, self.agent)
        # Presence missing (127) or other failure: fail closed — do not leave
        # inversion on without torch/notification/lease.
        if rc != 0:
            set_inversion(self.serial, False)
            raise ScreenControlError(
                "agent-presence on failed on %s (rc=%s): %s"
                % (self.host, rc, out.strip())
            )

        self.active = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.active:
            return False
        if self._skip:
            return False

        ssh_presence(self.host, "off", self.label, self.agent)
        if not set_inversion(self.serial, False):
            sys.stderr.write(
                "WARN: failed to disable display inversion on %s\n" % self.serial
            )
        if not restore_default_ime(self.serial, self._saved_ime):
            sys.stderr.write(
                "WARN: failed to restore keyboard IME on %s\n" % self.serial
            )
        self.active = False
        return False

    def shell(self, *args, **kwargs):
        return guarded_adb_shell(self.serial, self.active and not self._skip, *args, **kwargs)

    def tap(self, x, y):
        self.shell("input", "tap", str(x), str(y))

    def sleep(self, seconds):
        time.sleep(seconds)
