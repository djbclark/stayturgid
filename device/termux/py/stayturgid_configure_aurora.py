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
import stayturgid_handsets as hs
import stayturgid_screen_control as sc
from ui_parse import parse_button_center, parse_text_center

_HS: hs.Session | None = None

AURORA_PKG = "com.aurora.store"
BACKGROUND_DIALOG_MARKERS = (
    "Let app always run in background",
    "always run in the background",
)
BACKGROUND_DENY_LABELS = (
    "DENY",
    "Deny",
    "Don't allow",
    "Don't Allow",
    "DONT ALLOW",
    "Cancel",
)
# Prefer OS battery optimization so Aurora cannot thrash CPU in the background.
AURORA_BATTERY_APPOPS = (
    ("RUN_IN_BACKGROUND", "ignore"),
    ("RUN_ANY_IN_BACKGROUND", "ignore"),
)
FILTER_AURORA_ONLY_LABELS = (
    "Filter apps from other sources",
    "Do not check for updates for apps installed from sources outside Aurora Store",
    "Aurora Store apps only",
)
FILTER_FDROID_LABELS = (
    "Filter F-Droid apps",
    "Don't check updates for apps installed from F-Droid",
)
AUTO_UPDATE_RESTRICTION_LABELS = (
    "When device is idle",
    "When battery is not low",
)
# Prefer OFF — Check & install fights battery-optimized Aurora.
AUTO_UPDATE_OFF_LABELS = (
    "Do not auto-update apps",
    "Do not auto-update",
    "Don't auto-update",
    "Never",
    "Disable",
)
AUTO_UPDATE_ON_LABELS = (
    "Check & install available updates automatically",
    "Check and install available updates automatically",
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


def ensure_battery_optimized(shell):
    """Restore Doze / background limits — Aurora must not run unrestricted."""
    for op, mode in AURORA_BATTERY_APPOPS:
        shell("cmd", "appops", "set", AURORA_PKG, op, mode)
    shell("cmd", "deviceidle", "whitelist", "-%s" % AURORA_PKG)
    print("Aurora Store battery optimization restored.")


def dismiss_background_run_dialog(shell, app_hint="Aurora"):
    """Dismiss Settings 'run in background' modal with DENY/Back (keep battery opt)."""
    for _ in range(6):
        xml = dump_xml(shell)
        if not any(marker in xml for marker in BACKGROUND_DIALOG_MARKERS):
            return False
        if app_hint.lower() not in xml.lower():
            return False
        if _HS is not None:
            hit = _HS.tap_any_text(*BACKGROUND_DENY_LABELS)
            if hit:
                print("Tapped %s on background-run dialog (%s)." % (hit, app_hint))
                time.sleep(1.5)
                return True
            if _HS.tap_rid("android:id/button2"):
                print("Tapped DENY on background-run dialog (%s)." % app_hint)
                time.sleep(1.5)
                return True
            _HS.key("BACK")
            time.sleep(1)
            return True
        for label in BACKGROUND_DENY_LABELS:
            point = parse_text_center(xml, label)
            if point:
                print("Tapped %s on background-run dialog (%s)." % (label, app_hint))
                tap(shell, point)
                time.sleep(1.5)
                return True
        deny = parse_button_center(xml, "android:id/button2")
        if deny:
            print("Tapped DENY on background-run dialog (%s)." % app_hint)
            tap(shell, deny)
            time.sleep(1.5)
            return True
        shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
        return True
    return False


def ensure_preference_on(shell, labels, description, *, required=True):
    """Turn on the first matching preference switch among *labels*."""
    ui = dump_xml(shell)
    chosen = None
    for label in labels:
        if label in ui:
            chosen = label
            break
    if not chosen:
        msg = "could not find Aurora preference for %s (tried %r)" % (
            description,
            labels,
        )
        if required:
            sys.stderr.write("ERROR: %s\n" % msg)
        else:
            print("WARN: %s" % msg)
        return False

    if _HS is not None:
        checked, ok = _HS.switch_near_label(chosen)
        if ok and checked:
            print("Aurora %s already on (%s)." % (description, chosen))
            return True
        if not (_HS.tap_switch_for_label(chosen) or _HS.tap_text(chosen)):
            msg = "could not toggle Aurora %s (%s)" % (description, chosen)
            if required:
                sys.stderr.write("ERROR: %s\n" % msg)
            else:
                print("WARN: %s" % msg)
            return False
        time.sleep(1.5)
        checked, ok = _HS.switch_near_label(chosen)
        if not (ok and checked):
            msg = "Aurora %s still off after tap" % description
            if required:
                sys.stderr.write("ERROR: %s\n" % msg)
            else:
                print("WARN: %s" % msg)
            return False
        print("Aurora %s enabled (%s)." % (description, chosen))
        return True

    if not tap_text(shell, chosen, timeout=8):
        return False
    time.sleep(1)
    print("Aurora %s enabled (%s)." % (description, chosen))
    return True


def _aurora_home(ui: str) -> bool:
    """True when Aurora main UI is up (first-run finished)."""
    if "Skip" in ui or "btn_anonymous" in ui:
        return False
    # Handsets dump_text includes rid; XML dumps use resource-id="…".
    has_nav = (
        "nav_view" in ui
        or "nav_host_fragment" in ui
        or 'resource-id="com.aurora.store:id/nav_view"' in ui
        or "menu_more" in ui
    )
    if has_nav and any(t in ui for t in ("Apps", "Updates", "Library")):
        return True
    return "Apps" in ui and "Library" in ui


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
            if n.get("text") == "Shizuku installer" or "Shizuku installer" in str(n.get("text") or ""):
                # Prefer nearby checked radio/switch; fall back to any checked flag.
                if hs.Session._checked(n):
                    return True
        # Any checked node on the installation-method screen is enough when
        # the label is present (radio group).
        return "Shizuku installer" in ui_xml and any(hs.Session._checked(n) for n in _HS._walk_nodes())
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
    """Select Do not auto-update (compatible with battery-optimized Aurora)."""
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
    ui = dump_xml(shell)
    for lab in AUTO_UPDATE_OFF_LABELS:
        if lab in ui:
            if _HS is not None:
                checked, ok = _HS.switch_near_label(lab, timeout_ms=2000)
                if ok and checked:
                    print("Aurora Store automatic updates already off (%s)." % lab)
                    return True
            if tap_text(shell, lab, timeout=6):
                print("Aurora Store automatic updates set to off (%s)." % lab)
                return True
    for lab in AUTO_UPDATE_OFF_LABELS:
        if tap_text(shell, lab, timeout=4):
            print("Aurora Store automatic updates set to off (%s)." % lab)
            return True
    sys.stderr.write(
        "ERROR: could not select Do not auto-update (on_labels_present=%s)\n"
        % any(label in ui for label in AUTO_UPDATE_ON_LABELS)
    )
    return False


def configure_update_filters(shell):
    """Limit update checks to apps Aurora installed; also drop F-Droid packages."""
    for _ in range(3):
        ui = dump_xml(shell)
        if any(label in ui for label in FILTER_AURORA_ONLY_LABELS + FILTER_FDROID_LABELS):
            break
        if "Settings" in ui and "Updates" in ui:
            if not tap_text(shell, "Updates"):
                return False
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

    if not ensure_preference_on(shell, FILTER_AURORA_ONLY_LABELS, "filter apps from other sources"):
        return False
    if not ensure_preference_on(shell, FILTER_FDROID_LABELS, "filter F-Droid apps"):
        return False

    ui = dump_xml(shell)
    if "Automatic updates restrictions" in ui:
        if tap_text(shell, "Automatic updates restrictions", timeout=6):
            for label in AUTO_UPDATE_RESTRICTION_LABELS:
                ensure_preference_on(
                    shell,
                    (label,),
                    "auto-update restriction %s" % label,
                    required=False,
                )
    return True


def main(argv=None):
    global _HS
    del argv
    try:
        import ui_guard

        alias = sh.read_device_profile().get("alias") or "device"

        def detect_aurora_done():
            rc, out = sh.shell("cmd", "appops", "get", "com.aurora.store", "RUN_IN_BACKGROUND")
            return rc == 0 and "ignore" in (out or "")

        ui_guard.check_ui_guard(
            host=alias,
            action_type="AURORA-CONFIGURE",
            message=(
                "Please manually configure Aurora Store settings:\n"
                "1. Open Aurora Store and log in (anonymous).\n"
                "2. Navigate to Settings -> Updates -> disable Auto-updates.\n"
                "3. Navigate to Settings -> Filters -> enable 'Filter apps from other sources'."
            ),
            detect_fn=detect_aurora_done,
        )

        with sc.ScreenControlSession() as session:
            shell = session.shell
            with hs.try_session() as handsets:
                _HS = handsets
                ensure_battery_optimized(shell)
                open_aurora(shell)
                dismiss_background_run_dialog(shell)
                if not finish_first_run(shell):
                    return 1
                if not configure_installer(shell):
                    return 1
                if not configure_auto_updates(shell):
                    return 1
                if not configure_update_filters(shell):
                    return 1
                # Prior screen restored by ScreenControlSession.__exit__.
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _HS = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
