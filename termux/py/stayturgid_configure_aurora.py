#!/usr/bin/env python3
"""On-device Aurora Store first-run setup (Termux → Handsets / dump fallback).

Usage: stayturgid_configure_aurora.py
All input events go through ScreenControlSession.shell (inversion-gated).
"""
from __future__ import annotations

import re
import sys
import time
import xml.sax.saxutils as saxutils

import stayturgid_shell as sh

sh.ensure_lib_path()
import stayturgid_screen_control as sc  # noqa: E402
import stayturgid_handsets as hs  # noqa: E402
from ui_parse import parse_button_center, parse_text_center  # noqa: E402

_HS: hs.Session | None = None

AURORA_PKG = "com.aurora.store"
BACKGROUND_DIALOG_MARKERS = (
    "Let app always run in background",
    "always run in the background",
)
BACKGROUND_ALLOW_LABELS = ("ALLOW", "Allow", "Always allow", "ALWAYS ALLOW")
AURORA_BACKGROUND_APPOPS = (
    ("RUN_IN_BACKGROUND", "allow"),
    ("RUN_ANY_IN_BACKGROUND", "allow"),
    ("AUTO_REVOKE_PERMISSIONS_IF_UNUSED", "ignore"),
)


def dump_xml(shell):
    if _HS is not None:
        return _HS.dump_text()
    shell("uiautomator", "dump", "/sdcard/aurora_setup.xml")
    _rc, out = shell("cat", "/sdcard/aurora_setup.xml")
    return (out or "").replace("\r", "")


def center_for_attr(ui_xml, attr, value):
    if _HS is not None:
        return _HS.center_for(attr, value)
    value = saxutils.escape(value, {'"': "&quot;"})
    pattern = (
        r"<node\b(?=[^>]*\b%s=\"%s\")"
        r"[^>]*\bbounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"" % (re.escape(attr), re.escape(value))
    )
    match = re.search(pattern, ui_xml or "")
    if not match:
        return None
    x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def tap(shell, point):
    if _HS is not None:
        _HS.tap_xy(int(point[0]), int(point[1]))
        return
    shell("input", "tap", str(point[0]), str(point[1]))


def open_aurora(shell):
    shell("cmd", "package", "unsuspend", AURORA_PKG)
    shell("am", "force-stop", AURORA_PKG)
    time.sleep(1)
    if _HS is not None:
        _HS.key("HOME")
    else:
        shell("input", "keyevent", "KEYCODE_HOME")
    time.sleep(1)
    rc, _ = shell("am", "start", "-n", "%s/.MainActivity" % AURORA_PKG)
    if rc != 0:
        shell("monkey", "-p", AURORA_PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(3)


def ensure_background_unrestricted(shell):
    for op, mode in AURORA_BACKGROUND_APPOPS:
        shell("cmd", "appops", "set", AURORA_PKG, op, mode)
    shell("cmd", "deviceidle", "whitelist", "+%s" % AURORA_PKG)
    shell("am", "set-standby-bucket", AURORA_PKG, "active")
    print("Aurora Store background unrestricted via appops.")


def dismiss_background_run_dialog(shell, app_hint="Aurora"):
    for _ in range(6):
        xml = dump_xml(shell)
        if not any(marker in xml for marker in BACKGROUND_DIALOG_MARKERS):
            return False
        if app_hint.lower() not in xml.lower():
            return False
        if _HS is not None:
            hit = _HS.tap_any_text(*BACKGROUND_ALLOW_LABELS)
            if hit:
                print("Tapped %s on background-run dialog (%s)." % (hit, app_hint))
                time.sleep(1.5)
                return True
            if _HS.tap_rid("android:id/button1"):
                print("Tapped ALLOW on background-run dialog (%s)." % app_hint)
                time.sleep(1.5)
                return True
            return False
        allow = parse_button_center(xml, "android:id/button1")
        if allow:
            print("Tapped ALLOW on background-run dialog (%s)." % app_hint)
            tap(shell, allow)
            time.sleep(1.5)
            return True
        for label in BACKGROUND_ALLOW_LABELS:
            point = parse_text_center(xml, label)
            if point:
                print("Tapped %s on background-run dialog (%s)." % (label, app_hint))
                tap(shell, point)
                time.sleep(1.5)
                return True
    return False


def _aurora_home(ui: str) -> bool:
    """True when Aurora main UI is up (first-run finished)."""
    # Handsets dump_text includes rid; XML dumps use resource-id="…".
    has_nav = (
        "nav_view" in ui
        or "nav_host_fragment" in ui
        or 'resource-id="com.aurora.store:id/nav_view"' in ui
    )
    if has_nav and "Apps" in ui:
        return "Skip" not in ui and "btn_anonymous" not in ui
    return (
        "Apps" in ui
        and "Library" in ui
        and "Skip" not in ui
        and "btn_anonymous" not in ui
    )


def finish_first_run(shell):
    dismiss_background_run_dialog(shell)
    for _ in range(12):
        dismiss_background_run_dialog(shell)
        xml = dump_xml(shell)
        if _aurora_home(xml):
            print("Aurora Store first-run setup already complete.")
            return True
        if "anonymous@gmail.com" in xml and "Manage your account" in xml:
            cancel = center_for_attr(xml, "content-desc", "Cancel")
            if cancel:
                tap(shell, cancel)
            elif _HS is not None:
                _HS.key("BACK")
            else:
                shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(2)
            continue

        if "Allow Aurora Store to access Shizuku" in xml:
            if _HS is not None:
                if _HS.tap_rid("android:id/button1") or _HS.tap_text("Allow"):
                    time.sleep(2)
                    continue
            allow = parse_button_center(xml, "android:id/button1")
            if allow:
                tap(shell, allow)
                time.sleep(2)
                continue

        anonymous = center_for_attr(xml, "resource-id", "com.aurora.store:id/btn_anonymous")
        if anonymous:
            print("Tapped Aurora Anonymous.")
            tap(shell, anonymous)
            time.sleep(5)
            continue

        for label in ("Skip", "OK", "Continue"):
            point = center_for_attr(xml, "text", label)
            if point:
                print("Tapped Aurora %s." % label)
                tap(shell, point)
                time.sleep(2)
                break
        else:
            sys.stderr.write("ERROR: Aurora setup screen not recognized\n")
            return False

    sys.stderr.write("ERROR: Aurora setup did not reach home screen\n")
    return False


def wait_for_text(shell, text, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ui_xml = dump_xml(shell)
        if text in ui_xml:
            return ui_xml
        time.sleep(1)
    return dump_xml(shell)


def tap_text(shell, text, timeout=10):
    wait_for_text(shell, text, timeout)
    if _HS is not None:
        if _HS.tap_text(text):
            time.sleep(2)
            return True
        sys.stderr.write("ERROR: could not find Aurora text %r\n" % text)
        return False
    ui_xml = dump_xml(shell)
    point = center_for_attr(ui_xml, "text", text)
    if not point:
        sys.stderr.write("ERROR: could not find Aurora text %r\n" % text)
        return False
    tap(shell, point)
    time.sleep(2)
    return True


def open_settings(shell):
    ui_xml = dump_xml(shell)
    if "com.aurora.store" not in ui_xml and 'package="com.aurora.store"' not in ui_xml:
        open_aurora(shell)
        ui_xml = dump_xml(shell)
    more = center_for_attr(ui_xml, "resource-id", "com.aurora.store:id/menu_more")
    if not more:
        more = center_for_attr(ui_xml, "content-desc", "More")
    if not more:
        sys.stderr.write("ERROR: could not find Aurora More button\n")
        return False
    tap(shell, more)
    time.sleep(2)
    return tap_text(shell, "Settings")


def approve_shizuku_dialog(shell):
    ui_xml = dump_xml(shell)
    if "Allow Aurora Store to access Shizuku" not in ui_xml:
        return
    if _HS is not None:
        _HS.tap_rid("android:id/button1") or _HS.tap_text("Allow")
        time.sleep(2)
        return
    allow = parse_button_center(ui_xml, "android:id/button1")
    if allow:
        tap(shell, allow)
        time.sleep(2)


def _installer_checked(ui_xml: str) -> bool:
    if _HS is not None:
        for n in _HS._walk_nodes():
            if n.get("text") == "Shizuku installer" or "Shizuku installer" in str(
                n.get("text") or ""
            ):
                # Prefer nearby checked radio/switch; fall back to any checked flag.
                if hs.Session._checked(n):
                    return True
        # Any checked node on the installation-method screen is enough when
        # the label is present (radio group).
        return "Shizuku installer" in ui_xml and any(
            hs.Session._checked(n) for n in _HS._walk_nodes()
        )
    return "Shizuku installer" in ui_xml and 'checked="true"' in ui_xml


def configure_installer(shell):
    if not open_settings(shell):
        return False
    if not tap_text(shell, "Installation"):
        return False
    if not tap_text(shell, "Installation method"):
        return False
    if not tap_text(shell, "Shizuku installer"):
        return False
    approve_shizuku_dialog(shell)
    ui_xml = dump_xml(shell)
    if not _installer_checked(ui_xml):
        sys.stderr.write("ERROR: Aurora Shizuku installer was not selected\n")
        return False
    print("Aurora Store installer set to Shizuku.")
    return True


def configure_auto_updates(shell):
    for _ in range(3):
        ui_xml = dump_xml(shell)
        if "Settings" in ui_xml and "Updates" in ui_xml:
            break
        if _HS is not None:
            _HS.key("BACK")
        else:
            shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
    else:
        if not open_settings(shell):
            return False

    if not tap_text(shell, "Updates"):
        return False
    if not tap_text(shell, "Automatic updates"):
        return False
    if not tap_text(shell, "Check & install available updates automatically"):
        return False
    print("Aurora Store automatic updates enabled.")
    return True


def main(argv=None):
    global _HS
    del argv
    try:
        with sc.ScreenControlSession() as session:
            shell = session.shell
            with hs.try_session() as handsets:
                _HS = handsets
                ensure_background_unrestricted(shell)
                dismiss_background_run_dialog(shell)
                open_aurora(shell)
                dismiss_background_run_dialog(shell)
                if not finish_first_run(shell):
                    return 1
                if not configure_installer(shell):
                    return 1
                if not configure_auto_updates(shell):
                    return 1
                if _HS is not None:
                    _HS.key("HOME")
                else:
                    shell("input", "keyevent", "KEYCODE_HOME")
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _HS = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
