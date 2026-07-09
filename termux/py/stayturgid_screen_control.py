#!/usr/bin/env python3
"""On-device ScreenControlSession (Termux → localhost:5555).

Same policy as shared/mac/screen_control.py, but presence is a local
subprocess and adb is always localhost:5555. Fail closed when presence
script is missing (rc 127).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import stayturgid_shell as sh

sh.ensure_lib_path()
try:
    import ui_clearance as uc
except ImportError:
    from shared import ui_clearance as uc  # noqa: E402

INVERSION_KEY = "accessibility_display_inversion_enabled"
ADB_KEYBOARD = "com.github.uiautomator/.AdbKeyboard"
PRESENCE_PY = os.path.join(sh.STG, "bin", "stayturgid_agent_presence.py")
PRESENCE_SH = os.path.join(sh.STG, "bin", "agent-presence.sh")


class ScreenControlError(RuntimeError):
    pass


def is_input_command(args):
    if not args:
        return False
    if args[0] != "input":
        return False
    if len(args) < 2:
        return True
    return args[1] in ("tap", "swipe", "draganddrop", "text", "keyevent", "roll")


def inversion_enabled(_serial=None):
    rc, out = sh.shell("settings", "get", "secure", INVERSION_KEY)
    return rc == 0 and out.strip() == "1"


def set_inversion(_serial, enabled):
    state = "1" if enabled else "0"
    rc, _ = sh.shell("settings", "put", "secure", INVERSION_KEY, state)
    return rc == 0 and inversion_enabled() == enabled


def get_default_ime(_serial=None):
    rc, out = sh.shell("settings", "get", "secure", "default_input_method")
    if rc != 0:
        return None
    ime = out.strip()
    return ime if ime and ime != "null" else None


def set_default_ime(_serial, ime):
    if not ime or ime == "null":
        return False
    sh.shell("ime", "enable", ime)
    rc, _ = sh.shell("settings", "put", "secure", "default_input_method", ime)
    return rc == 0 and get_default_ime() == ime


def restore_default_ime(_serial, saved_ime):
    if not saved_ime:
        return True
    cur = get_default_ime()
    if cur == saved_ime:
        return True
    if cur != ADB_KEYBOARD and cur:
        return True
    return set_default_ime(None, saved_ime)


def _presence_cmd():
    if os.path.isfile(PRESENCE_PY):
        return ["python3", PRESENCE_PY]
    if os.path.isfile(PRESENCE_SH) and os.access(PRESENCE_SH, os.X_OK):
        return [PRESENCE_SH]
    return None


def local_presence(action, label, agent):
    cmd = _presence_cmd()
    if not cmd:
        return 127, "presence script missing under ~/.stayturgid/bin/"
    try:
        r = subprocess.run(
            cmd + [action, label, agent],
            capture_output=True,
            text=True,
            timeout=90 if action == "request-screen" else 30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def guarded_shell(active, *args, timeout=30):
    if active and is_input_command(args) and not inversion_enabled():
        raise ScreenControlError(
            "refusing adb input: accessibility display inversion is off "
            "(screen-control session required)"
        )
    return sh.shell(*args, timeout=timeout)


class ScreenControlSession(object):
    """Consent + inverted screen for on-device UI automation."""

    def __init__(self, label=None, agent=None, skip_request=False):
        self.serial = sh.SERIAL
        self.label = label or sh.device_label()
        self.agent = agent or os.environ.get("STAYTURGID_AGENT", "Auto")
        self.skip_request = skip_request
        self.active = False
        self._skip = os.environ.get("STAYTURGID_SKIP_PRESENCE") == "1"
        self._saved_ime = None

    def __enter__(self):
        if not sh.privileged_shell_expected():
            raise ScreenControlError(
                "privileged localhost:5555 not expected on this host "
                "(use Mac USB adb path)"
            )
        if not sh.privileged_shell_ok():
            raise ScreenControlError(
                "localhost:5555 shell unavailable — run stayturgid-repair first"
            )

        if self._skip:
            sys.stderr.write(
                "WARN: STAYTURGID_SKIP_PRESENCE=1 — input not gated by inversion\n"
            )
            self.active = True
            return self

        cleared = uc.clear_ui_obstructions(self.serial, sh.shell_fn)
        if cleared:
            print("Cleared UI obstructions: %s" % ", ".join(cleared))
        self._saved_ime = get_default_ime()

        if not self.skip_request:
            rc, out = local_presence("request-screen", self.label, self.agent)
            if rc == 75:
                raise ScreenControlError("screen control denied")
            if rc != 0:
                raise ScreenControlError(
                    "request-screen failed (rc=%s): %s" % (rc, out.strip())
                )

        if not set_inversion(None, True):
            raise ScreenControlError("failed to enable display inversion")

        rc, out = local_presence("on", self.label, self.agent)
        if rc != 0:
            sys.stderr.write(
                "WARN: agent-presence on failed (rc=%s): %s\n" % (rc, out.strip())
            )

        self.active = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.active:
            return False
        if self._skip:
            return False
        local_presence("off", self.label, self.agent)
        if not set_inversion(None, False):
            sys.stderr.write("WARN: failed to disable display inversion\n")
        if not restore_default_ime(None, self._saved_ime):
            sys.stderr.write("WARN: failed to restore keyboard IME\n")
        self.active = False
        return False

    def shell(self, *args, **kwargs):
        return guarded_shell(self.active and not self._skip, *args, **kwargs)

    def tap(self, x, y):
        self.shell("input", "tap", str(x), str(y))

    def sleep(self, seconds):
        time.sleep(seconds)
