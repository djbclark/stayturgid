#!/usr/bin/env python3
"""Mandatory screen-control session for Mac-side UI automation.

All stayturgid Mac scripts that send input events (tap, swipe, keyevent) must
run inside ScreenControlSession. The session:

  1. Clears PiP / floating overlays that can steal taps (dumpsys + dismiss).
  2. Locks natural **portrait** (auto-rotate off; restores prefs on exit).
  3. Requests consent on-device (agent-presence request-screen).
  4. Turns on accessibility display inversion (Mac adb — authoritative).
  5. Starts the on-device presence indicator (torch, notification via SSH).
  6. Refuses further input if inversion is off (fail closed).
  7. On exit (batch endpoint): best-effort restore of the foreground
     activity that was showing when the session started, then inversion
     off + presence off + rotation prefs restored.

Raw `adb shell input …` outside this wrapper can still bypass the policy;
project scripts must not do that.

STAYTURGID_SKIP_PRESENCE=1 (debug only): skips consent countdown and
torch/notification lease, but **still enables display inversion** and
**still refuses input when inversion is off**. Never use it to hide active
UI work on a phone a human is watching.

STAYTURGID_PRESENCE_QUIET=1 (scheduled audits): keeps inversion + lease, but
skips torch, vibrate, consent dialog, and presence notifications. Prefer this
over SKIP_PRESENCE for overnight GUI jobs.
"""

import os
import re
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import device_screen_lease as dsl
import stayturgid_device as dev
import ui_clearance as uc

INPUT_PREFIXES = ("input",)
INVERSION_KEY = "accessibility_display_inversion_enabled"
ADB_KEYBOARD = "com.github.uiautomator/.AdbKeyboard"
# Fleet layout deploys presence scripts under ~/.stayturgid/bin/ (not ~/).
PRESENCE_SCRIPT = "~/.stayturgid/bin/stayturgid_agent_presence.py"
# Pre-OPTIONS-62 deploy path (removed from deploy list; still tried as fallback).
PRESENCE_SCRIPT_LEGACY = "~/.stayturgid/bin/agent-presence.sh"
# Re-assert inversion + extend presence lease during long held batches
# (gaps between dependent UI steps where we are not tapping).
HOLD_KEEPALIVE_SEC = 45
# Portrait lock while the session holds the glass (user_rotation degrees).
PORTRAIT_USER_ROTATION = 0
_ROTATION_KEYS = ("accelerometer_rotation", "user_rotation")


# pkg/activity from dumpsys window / activity lines.
_FOCUS_COMPONENT_RE = re.compile(
    r"(?:mCurrentFocus|mFocusedApp|mResumedActivity|topResumedActivity)"
    r".*?\b([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/([A-Za-z0-9_$.]+)"
)
# Packages where HOME is a better restore than restarting the activity.
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
    rc, _out = mac_adb_shell(serial, "settings", "put", "secure", INVERSION_KEY, state)
    return rc == 0 and inversion_enabled(serial) == enabled


class SettingsReadError(Exception):
    pass


def _get_system_setting(serial, key):
    rc, out = mac_adb_shell(serial, "settings", "get", "system", key)
    if rc != 0:
        raise SettingsReadError(f"settings get {key} failed with rc={rc}")
    val = out.strip()
    if not val or val == "null":
        return "null"
    return val


def read_rotation_settings(serial):
    """Current system rotation prefs (accelerometer_rotation, user_rotation)."""
    try:
        return {k: _get_system_setting(serial, k) for k in _ROTATION_KEYS}
    except SettingsReadError:
        return None


def apply_portrait_lock(serial):
    """Disable auto-rotate and pin natural portrait (user_rotation=0).

    Uses system settings plus best-effort ``cmd window set-user-rotation`` /
    ``wm set-user-rotation`` so OEM UIs that ignore settings still settle.
    """
    ok = True
    for key, val in (
        ("accelerometer_rotation", "0"),
        ("user_rotation", str(PORTRAIT_USER_ROTATION)),
    ):
        rc, _out = mac_adb_shell(serial, "settings", "put", "system", key, val, timeout=10)
        ok = ok and rc == 0
    # Android 11+ window window (ignore failures on older builds).
    for args in (
        ("cmd", "window", "set-user-rotation", "lock", str(PORTRAIT_USER_ROTATION)),
        ("wm", "set-user-rotation", "lock", str(PORTRAIT_USER_ROTATION)),
        ("wm", "user-rotation", "lock", str(PORTRAIT_USER_ROTATION)),
    ):
        rc, _out = mac_adb_shell(serial, *args, timeout=10)
        if rc == 0:
            break
    return ok


def lock_portrait_orientation(serial):
    """Save rotation prefs, then lock portrait for the session."""
    saved = read_rotation_settings(serial)
    if saved is None:
        sys.stderr.write("WARN: failed to read rotation settings, aborting portrait lock on %s\n" % serial)
        return None
    if not apply_portrait_lock(serial):
        sys.stderr.write("WARN: failed to lock portrait orientation on %s\n" % serial)
    return saved


def restore_rotation_settings(serial, saved):
    """Restore rotation prefs captured at session start."""
    if not saved:
        return True
    ok = True
    # Free any window-manager lock before restoring settings values.
    for args in (
        ("cmd", "window", "set-user-rotation", "free"),
        ("wm", "set-user-rotation", "free"),
        ("wm", "user-rotation", "free"),
    ):
        rc, _out = mac_adb_shell(serial, *args, timeout=10)
        if rc == 0:
            break
    for key in _ROTATION_KEYS:
        val = saved.get(key)
        if val is None:
            continue
        if val == "null":
            mac_adb_shell(serial, "settings", "delete", "system", key, timeout=10)
        else:
            mac_adb_shell(serial, "settings", "put", "system", key, val, timeout=10)
        ok = ok and rc == 0
    if not ok:
        sys.stderr.write("WARN: failed to restore rotation settings on %s\n" % serial)
    return ok


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
    rc, _out = mac_adb_shell(serial, "settings", "put", "secure", "default_input_method", ime)
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


def parse_foreground_component(dumpsys_text):
    """Return 'pkg/activity' from dumpsys window/activity text, or None."""
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


def get_foreground_component(serial):
    """Best-effort focused activity (pkg/cls) before we steal the glass."""
    for args in (
        ("dumpsys", "window", "windows"),
        ("dumpsys", "window"),
        ("dumpsys", "activity", "activities"),
    ):
        rc, out = mac_adb_shell(serial, *args, timeout=20)
        if rc != 0 or not out:
            continue
        comp = parse_foreground_component(out)
        if comp:
            return comp
    return None


def restore_foreground(serial, component, shell_fn=None):
    """Return to the pre-session screen at a batch endpoint.

    Launchers → HOME. Real activities → ``am start`` that component.
    Soft-fails (returns False) rather than raising — cleanup must continue.
    """
    run = shell_fn or (lambda *a, **k: mac_adb_shell(serial, *a, **k))
    if not component or "/" not in component:
        rc, _ = run("input", "keyevent", "KEYCODE_HOME", timeout=10)
        return rc == 0
    pkg = component.split("/", 1)[0]
    if pkg in _LAUNCHER_OR_IDLE_PKGS or pkg.endswith(".launcher"):
        rc, _ = run("input", "keyevent", "KEYCODE_HOME", timeout=10)
        return rc == 0
    # Prefer bringing the existing task forward over a cold launch.
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


def ssh_presence(host, action, label, agent):
    host = dev.resolve_ssh_host(host) or host
    if not host:
        return 127, "no ssh host"
    quiet = os.environ.get("STAYTURGID_PRESENCE_QUIET") == "1"
    quiet_export = "export STAYTURGID_PRESENCE_QUIET=1; " if quiet else ""
    # Prefer single-root deploy path; fall back to legacy ~/ shim if present.
    remote = '%sif [ -x %s ]; then P=%s; elif [ -x %s ]; then P=%s; else exit 127; fi; "$P" %s %s %s' % (
        quiet_export,
        PRESENCE_SCRIPT,
        PRESENCE_SCRIPT,
        PRESENCE_SCRIPT_LEGACY,
        PRESENCE_SCRIPT_LEGACY,
        action,
        _shell_quote(label),
        _shell_quote(agent),
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


class ScreenControlSession:
    """Context manager: consent + inverted screen for UI automation."""

    def __init__(
        self,
        host,
        label=None,
        agent=None,
        skip_request=False,
        restore_screen=True,
    ):
        self.host = host
        self.serial = dev.resolve_adb(host)
        self.label = label or host
        self.agent = agent or os.environ.get("STAYTURGID_AGENT", "Auto")
        self.skip_request = skip_request
        # At batch endpoint (__exit__), try to put the prior app back on screen.
        self.restore_screen = bool(restore_screen)
        self.active = False
        self._skip = os.environ.get("STAYTURGID_SKIP_PRESENCE") == "1"
        self._saved_ime = None
        self._saved_component = None
        self._saved_rotation = None
        self._stop_keepalive = threading.Event()
        self._keepalive_thread = None
        self._lease_session_id = None
        self._lease_acquired = False
        self.purpose = os.environ.get("STAYTURGID_SCREEN_PURPOSE", "ui-automation")

    def _device_ids_for_lease(self):
        ids = [self.host, self.serial]
        try:
            row = dev.device_row(self.host)
            if row:
                usb, ts_ip, lan = row
                if usb and usb != "-":
                    ids.append(usb)
                if ts_ip and ts_ip != "-":
                    ids.append("%s:5555" % ts_ip)
                if lan and lan != "-":
                    ids.append("%s:5555" % lan)
        except Exception:
            pass
        return ids

    def _acquire_cross_project_lease(self):
        """Mac-side DSCL lease so other projects see we hold the glass."""
        try:
            lease = dsl.acquire(
                self.host,
                device_ids=self._device_ids_for_lease(),
                purpose=self.purpose,
                agent=self.agent,
                project=dsl.project_id(),
            )
            self._lease_session_id = lease.get("holder", {}).get("session_id")
            self._lease_acquired = True
            print("screen-lease acquired %s (%s)" % (self.host, dsl.format_holder(lease)))
        except dsl.LeaseConflict as e:
            raise ScreenControlError(
                "screen control blocked on %s — %s. "
                "Wait for the other project to FREE the device, or set "
                "DEVICE_SCREEN_CONTROL_FORCE=1 / STAYTURGID_SCREEN_LEASE_FORCE=1 "
                "only if you intentionally steal the glass." % (self.host, e)
            ) from e

    def _release_cross_project_lease(self):
        if not self._lease_acquired:
            return
        try:
            dsl.release(self.host, session_id=self._lease_session_id)
        except Exception as e:
            sys.stderr.write("WARN: screen-lease release on %s: %s\n" % (self.host, e))
        self._lease_acquired = False

    def _keepalive_loop(self):
        """Keep inversion on + presence lease fresh across idle gaps in a batch."""
        while not self._stop_keepalive.wait(HOLD_KEEPALIVE_SEC):
            if not self.active:
                return
            try:
                if not inversion_enabled(self.serial):
                    if set_inversion(self.serial, True):
                        sys.stderr.write("WARN: re-enabled display inversion on %s (hold keepalive)\n" % self.host)
                if not self._skip:
                    # Extend lease without torch/dialog (quiet if already quiet).
                    ssh_presence(self.host, "guard", self.label, self.agent)
                if self._lease_acquired:
                    dsl.heartbeat(self.host, session_id=self._lease_session_id)
                apply_portrait_lock(self.serial)
            except Exception as e:
                sys.stderr.write("WARN: screen-control keepalive on %s: %s\n" % (self.host, e))

    def _start_keepalive(self):
        self._stop_keepalive.clear()
        t = threading.Thread(
            target=self._keepalive_loop,
            name="screen-control-keepalive-%s" % self.host,
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
        # Cross-project lease first — fail before consent/inversion if busy.
        self._acquire_cross_project_lease()
        try:
            return self._enter_session()
        except Exception:
            self._release_cross_project_lease()
            raise

    def _enter_session(self):
        _run(["adb", "connect", self.serial], timeout=15)
        _run(["adb", "-s", self.serial, "wait-for-device"], timeout=30)
        # Capture before clearance/consent so we restore what the human saw.
        # DISABLED 2026-07-14 (H9): foreground save/restore is unreliable across
        # different launchers and Android versions. Commented out for now; may add
        # back via FIRERPA OCR/screen-control when the approach is more robust.
        # self._saved_component = get_foreground_component(self.serial)
        self._saved_rotation = lock_portrait_orientation(self.serial)
        cleared = uc.clear_ui_obstructions(self.serial, mac_adb_shell)
        if cleared:
            print("Cleared UI obstructions on %s: %s" % (self.host, ", ".join(cleared)))
        self._saved_ime = get_default_ime(self.serial)

        if self._skip:
            sys.stderr.write(
                "WARN: STAYTURGID_SKIP_PRESENCE=1 — skipping consent/torch; display inversion still required\n"
            )
        elif not self.skip_request:
            rc, out = ssh_presence(self.host, "request-screen", self.label, self.agent)
            if rc == 75:
                raise ScreenControlError("screen control denied on %s" % self.host)
            # rc 127 = presence script missing — fail closed (do not skip consent).
            if rc != 0:
                raise ScreenControlError("request-screen failed on %s (rc=%s): %s" % (self.host, rc, out.strip()))

        # Inversion is the visible "agent has the glass" signal — always on,
        # including SKIP_PRESENCE. Input stays gated on inversion.
        if not set_inversion(self.serial, True):
            raise ScreenControlError("failed to enable display inversion on %s" % self.serial)

        if not self._skip:
            rc, out = ssh_presence(self.host, "on", self.label, self.agent)
            # Presence missing (127) or other failure: fail closed — do not leave
            # inversion on without torch/notification/lease.
            if rc != 0:
                set_inversion(self.serial, False)
                raise ScreenControlError("agent-presence on failed on %s (rc=%s): %s" % (self.host, rc, out.strip()))

        self.active = True
        self._start_keepalive()
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.active:
            return False

        self._stop_keepalive_thread()

        # DISABLED 2026-07-14 (H9): foreground save/restore is unreliable.
        # Kept for reference; see comment in _enter_session().
        # if self.restore_screen:
        #     try:
        #         ok = restore_foreground(
        #             self.serial,
        #             self._saved_component,
        #             shell_fn=self.shell,
        #         )
        #         if ok and self._saved_component:
        #             print("Restored prior screen on %s: %s" % (self.host, self._saved_component))
        #         elif not ok:
        #             sys.stderr.write(
        #                 "WARN: failed to restore prior screen on %s (%s)\n"
        #                 % (self.host, self._saved_component or "HOME")
        #             )
        #     except Exception as e:
        #         sys.stderr.write("WARN: restore prior screen on %s: %s\n" % (self.host, e))

        if not self._skip:
            ssh_presence(self.host, "off", self.label, self.agent)
        if not set_inversion(self.serial, False):
            sys.stderr.write("WARN: failed to disable display inversion on %s\n" % self.serial)
        if not restore_default_ime(self.serial, self._saved_ime):
            sys.stderr.write("WARN: failed to restore keyboard IME on %s\n" % self.serial)
        restore_rotation_settings(self.serial, self._saved_rotation)
        self._release_cross_project_lease()
        self.active = False
        return False

    def shell(self, *args, **kwargs):
        return guarded_adb_shell(self.serial, self.active, *args, **kwargs)

    def tap(self, x, y):
        self.shell("input", "tap", str(x), str(y))

    def sleep(self, seconds):
        time.sleep(seconds)
