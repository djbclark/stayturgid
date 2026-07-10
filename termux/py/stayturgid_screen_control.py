#!/usr/bin/env python3
"""On-device ScreenControlSession (Termux → localhost:5555).

Same policy as shared/mac/screen_control.py, but presence is a local
subprocess and adb is always localhost:5555. Fail closed when presence
script is missing (rc 127).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
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
HOLD_KEEPALIVE_SEC = 45

_FOCUS_COMPONENT_RE = re.compile(
    r"(?:mCurrentFocus|mFocusedApp|mResumedActivity|topResumedActivity)"
    r".*?\b([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/([A-Za-z0-9_$.]+)"
)
_LAUNCHER_OR_IDLE_PKGS = frozenset(
    {
        "com.sec.android.app.launcher",
        "com.google.android.apps.nexuslauncher",
        "com.android.launcher3",
        "com.android.systemui",
        "com.samsung.android.app.aodservice",
        "com.amazon.firelauncher",
        "com.amazon.alerter",
    }
)


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


def parse_foreground_component(dumpsys_text):
    if not dumpsys_text:
        return None
    for line in dumpsys_text.splitlines():
        if not any(
            k in line
            for k in (
                "mCurrentFocus",
                "mFocusedApp",
                "mResumedActivity",
                "topResumedActivity",
            )
        ):
            continue
        m = _FOCUS_COMPONENT_RE.search(line)
        if m:
            return "%s/%s" % (m.group(1), m.group(2))
    return None


def get_foreground_component(_serial=None):
    for args in (
        ("dumpsys", "window", "windows"),
        ("dumpsys", "window"),
        ("dumpsys", "activity", "activities"),
    ):
        rc, out = sh.shell(*args, timeout=20)
        if rc != 0 or not out:
            continue
        comp = parse_foreground_component(out)
        if comp:
            return comp
    return None


def restore_foreground(_serial, component, shell_fn=None):
    run = shell_fn or (lambda *a, **k: sh.shell(*a, **k))
    if not component or "/" not in component:
        rc, _ = run("input", "keyevent", "KEYCODE_HOME", timeout=10)
        return rc == 0
    pkg = component.split("/", 1)[0]
    if pkg in _LAUNCHER_OR_IDLE_PKGS or pkg.endswith(".launcher"):
        rc, _ = run("input", "keyevent", "KEYCODE_HOME", timeout=10)
        return rc == 0
    rc, _ = run(
        "am",
        "start",
        "--activity-single-top",
        "--activity-brought-to-front",
        "-n",
        component,
        timeout=15,
    )
    if rc == 0:
        return True
    rc, _ = run("am", "start", "-n", component, timeout=15)
    return rc == 0


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

    def __init__(self, label=None, agent=None, skip_request=False, restore_screen=True):
        self.serial = sh.SERIAL
        self.label = label or sh.device_label()
        self.agent = agent or os.environ.get("STAYTURGID_AGENT", "Auto")
        self.skip_request = skip_request
        self.restore_screen = bool(restore_screen)
        self.active = False
        self._skip = os.environ.get("STAYTURGID_SKIP_PRESENCE") == "1"
        self._saved_ime = None
        self._saved_component = None
        self._stop_keepalive = threading.Event()
        self._keepalive_thread = None

    def _keepalive_loop(self):
        while not self._stop_keepalive.wait(HOLD_KEEPALIVE_SEC):
            if not self.active:
                return
            try:
                if not inversion_enabled():
                    if set_inversion(None, True):
                        sys.stderr.write(
                            "WARN: re-enabled display inversion (hold keepalive)\n"
                        )
                if not self._skip:
                    local_presence("guard", self.label, self.agent)
            except Exception as e:  # noqa: BLE001
                sys.stderr.write("WARN: screen-control keepalive: %s\n" % e)

    def _start_keepalive(self):
        self._stop_keepalive.clear()
        t = threading.Thread(
            target=self._keepalive_loop,
            name="screen-control-keepalive",
            daemon=True,
        )
        self._keepalive_thread = t
        t.start()

    def _stop_keepalive_thread(self):
        self._stop_keepalive.set()
        t = self._keepalive_thread
        self._keepalive_thread = None
        if t is not None and t.is_alive():
            t.join(timeout=2.0)

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

        self._saved_component = get_foreground_component()
        cleared = uc.clear_ui_obstructions(self.serial, sh.shell_fn)
        if cleared:
            print("Cleared UI obstructions: %s" % ", ".join(cleared))
        self._saved_ime = get_default_ime()

        if self._skip:
            sys.stderr.write(
                "WARN: STAYTURGID_SKIP_PRESENCE=1 — skipping consent/torch; "
                "display inversion still required\n"
            )
        elif not self.skip_request:
            rc, out = local_presence("request-screen", self.label, self.agent)
            if rc == 75:
                raise ScreenControlError("screen control denied")
            if rc != 0:
                raise ScreenControlError(
                    "request-screen failed (rc=%s): %s" % (rc, out.strip())
                )

        # Inversion is the visible "agent has the glass" signal — always on.
        if not set_inversion(None, True):
            raise ScreenControlError("failed to enable display inversion")

        if not self._skip:
            rc, out = local_presence("on", self.label, self.agent)
            if rc != 0:
                set_inversion(None, False)
                raise ScreenControlError(
                    "agent-presence on failed (rc=%s): %s" % (rc, out.strip())
                )

        self.active = True
        self._start_keepalive()
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.active:
            return False
        self._stop_keepalive_thread()
        if self.restore_screen:
            try:
                ok = restore_foreground(
                    self.serial,
                    self._saved_component,
                    shell_fn=self.shell,
                )
                if ok and self._saved_component:
                    print("Restored prior screen: %s" % self._saved_component)
                elif not ok:
                    sys.stderr.write(
                        "WARN: failed to restore prior screen (%s)\n"
                        % (self._saved_component or "HOME")
                    )
            except Exception as e:  # noqa: BLE001
                sys.stderr.write("WARN: restore prior screen: %s\n" % e)
        if not self._skip:
            local_presence("off", self.label, self.agent)
        if not set_inversion(None, False):
            sys.stderr.write("WARN: failed to disable display inversion\n")
        if not restore_default_ime(None, self._saved_ime):
            sys.stderr.write("WARN: failed to restore keyboard IME\n")
        self.active = False
        return False

    def shell(self, *args, **kwargs):
        return guarded_shell(self.active, *args, **kwargs)

    def tap(self, x, y):
        self.shell("input", "tap", str(x), str(y))

    def sleep(self, seconds):
        time.sleep(seconds)
