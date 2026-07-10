#!/usr/bin/env python3
"""Finish Aurora Store first-run setup from the Mac.

Usage: ./play/mac/configure_aurora.py <s24|hd8|p7a|serial>

Skips the intro carousel, selects Aurora's anonymous session, and configures the
installer/update settings needed for unattended installs. Called automatically at
the end of deploy_fleet.py (--scope full or play).
"""
import os
import re
import subprocess
import sys
import time
import xml.sax.saxutils as saxutils

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402
import post_ui_remote as remote  # noqa: E402
import ui_driver as uid  # noqa: E402

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
# AUTO_REVOKE ignore is applied via fleet_app_profiles (harden), not Doze whitelist.
AURORA_BATTERY_APPOPS = (
    ("RUN_IN_BACKGROUND", "ignore"),
    ("RUN_ANY_IN_BACKGROUND", "ignore"),
)
# Updates filter switches (Aurora 4.8+ labels). Prefer primary; fall back to aliases.
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

# Bound inside ScreenControlSession so input is inversion-gated.
_SHELL = None
# Optional Handsets session — primary Mac UI path; raw dump fallback.
_HS = None


def adb(serial, *args, timeout=30):
    if _SHELL is not None:
        rc, out = _SHELL(*args, timeout=timeout)
        class _R(object):
            returncode = rc
            stdout = out
        return _R()
    return subprocess.run(
        ["adb", "-s", serial, "shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def dump_xml(serial):
    adb(serial, "uiautomator", "dump", "/sdcard/aurora_setup.xml")
    result = adb(serial, "cat", "/sdcard/aurora_setup.xml")
    return result.stdout.replace("\r", "")


def center_for_attr(ui_xml, attr, value):
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


def tap(serial, point):
    adb(serial, "input", "tap", str(point[0]), str(point[1]))


def open_aurora(serial):
    adb(serial, "cmd", "package", "unsuspend", AURORA_PKG)
    adb(serial, "am", "force-stop", AURORA_PKG)
    time.sleep(1)
    adb(serial, "input", "keyevent", "KEYCODE_HOME")
    time.sleep(1)
    result = adb(serial, "am", "start", "-n", "%s/.MainActivity" % AURORA_PKG)
    if result.returncode != 0:
        adb(serial, "monkey", "-p", AURORA_PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(3)


def ensure_battery_optimized(serial):
    """Restore Doze / background limits — Aurora must not run unrestricted."""
    for op, mode in AURORA_BATTERY_APPOPS:
        adb(serial, "cmd", "appops", "set", AURORA_PKG, op, mode)
    adb(serial, "cmd", "deviceidle", "whitelist", "-%s" % AURORA_PKG)
    # Don't force standby bucket active; leave OS scheduling alone.
    print("Aurora Store battery optimization restored on %s." % serial)


def _switch_checked_xml(ui_xml, label):
    """Best-effort: Switch/CheckBox near label text is checked."""
    if label not in (ui_xml or ""):
        return None
    # Prefer a checked=true node whose line/context mentions the label.
    for m in re.finditer(
        r"<node\b[^>]*\btext=\"%s\"[^>]*>" % re.escape(saxutils.escape(label, {'"': "&quot;"})),
        ui_xml or "",
    ):
        # Look ahead for a sibling Switch with checked in the next ~800 chars.
        window = ui_xml[m.start() : m.start() + 1200]
        if 'class="android.widget.Switch"' in window or "Switch" in window:
            if 'checked="true"' in window:
                return True
            if 'checked="false"' in window:
                return False
    if 'checked="true"' in (ui_xml or "") and label in ui_xml:
        # Ambiguous when multiple switches — treat as unknown.
        return None
    return None


def ensure_preference_on(serial, labels, description, *, required=True):
    """Turn on the first matching preference switch among *labels*.

    When *required* is False, missing or stuck switches warn and return False
    without failing the overall configure run.
    """
    ui = _ui_text(serial)
    chosen = None
    for label in labels:
        if label in ui:
            chosen = label
            break
    if not chosen:
        msg = (
            "could not find Aurora preference for %s on %s (tried %r)"
            % (description, serial, labels)
        )
        if required:
            sys.stderr.write("ERROR: %s\n" % msg)
        else:
            print("WARN: %s" % msg)
        return False

    if _HS is not None:
        checked, ok = _HS.switch_near_label(chosen, timeout_ms=3000)
        if ok and checked:
            print("Aurora %s already on (%s)." % (description, chosen))
            return True
        if not (
            _HS.tap_switch_for_label(chosen, timeout_ms=4000)
            or _HS.tap_text(chosen, timeout_ms=2000)
        ):
            msg = "could not toggle Aurora %s (%s) on %s" % (
                description,
                chosen,
                serial,
            )
            if required:
                sys.stderr.write("ERROR: %s\n" % msg)
            else:
                print("WARN: %s" % msg)
            return False
        time.sleep(1.5)
        checked, ok = _HS.switch_near_label(chosen, timeout_ms=3000)
        if not (ok and checked):
            msg = "Aurora %s still off after tap on %s" % (description, serial)
            if required:
                sys.stderr.write("ERROR: %s\n" % msg)
            else:
                print("WARN: %s" % msg)
            return False
        print("Aurora %s enabled (%s)." % (description, chosen))
        return True

    checked = _switch_checked_xml(ui, chosen)
    if checked is True:
        print("Aurora %s already on (%s)." % (description, chosen))
        return True
    if not tap_text(serial, chosen, timeout=8):
        return False
    time.sleep(1)
    print("Aurora %s enabled (%s)." % (description, chosen))
    return True


def _ui_text(serial):
    if _HS is not None:
        return _HS.ui()
    return dump_xml(serial)


def dismiss_background_run_dialog(serial, app_hint="Aurora"):
    """Dismiss Settings 'run in background' modal with DENY/Back (keep battery opt)."""
    for _ in range(6):
        ui = _ui_text(serial)
        if not any(marker in ui for marker in BACKGROUND_DIALOG_MARKERS):
            return False
        if app_hint.lower() not in ui.lower():
            return False
        if _HS is not None:
            hit = _HS.tap_any_text(*BACKGROUND_DENY_LABELS, timeout_ms=2000)
            if hit:
                print("Tapped %s on background-run dialog (%s)." % (hit, app_hint))
                time.sleep(1.5)
                return True
            adb(serial, "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1)
            return True
        for label in BACKGROUND_DENY_LABELS:
            point = dev.parse_text_center(ui, label) or center_for_attr(ui, "text", label)
            if point:
                print("Tapped %s on background-run dialog (%s)." % (label, app_hint))
                tap(serial, point)
                time.sleep(1.5)
                return True
        deny = center_for_attr(ui, "resource-id", "android:id/button2")
        if deny:
            print("Tapped DENY on background-run dialog (%s)." % app_hint)
            tap(serial, deny)
            time.sleep(1.5)
            return True
        adb(serial, "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
        return True
    return False


def _aurora_home(ui: str) -> bool:
    """True when Aurora main UI is up (Apps/Updates/Library tabs, first-run done)."""
    if "Skip" in ui or "btn_anonymous" in ui:
        return False
    if "menu_more" in ui or "More" in ui:
        if any(t in ui for t in ("Apps", "Updates", "Library", "nav_view", "nav_host")):
            return True
    return ("nav_view" in ui and "Apps" in ui) or (
        "Apps" in ui and "Library" in ui
    )


def finish_first_run(serial):
    dismiss_background_run_dialog(serial)
    for _ in range(12):
        dismiss_background_run_dialog(serial)
        ui = _ui_text(serial)
        if _aurora_home(ui):
            print("Aurora Store first-run setup already complete on %s." % serial)
            return True

        if _HS is not None:
            if "anonymous@gmail.com" in ui and "Manage your account" in ui:
                if not _HS.tap_desc("Cancel", timeout_ms=1500):
                    adb(serial, "input", "keyevent", "KEYCODE_BACK")
                time.sleep(2)
                continue
            if "Allow Aurora Store to access Shizuku" in ui and _HS.tap_text(
                "Allow", timeout_ms=2000
            ):
                time.sleep(2)
                continue
            if _HS.tap_id("com.aurora.store:id/btn_anonymous", timeout_ms=2000):
                print("Tapped Aurora Anonymous on %s." % serial)
                time.sleep(5)
                continue
            hit = _HS.tap_any_text("Skip", "OK", "Continue", timeout_ms=1500)
            if hit:
                print("Tapped Aurora %s on %s." % (hit, serial))
                time.sleep(2)
                continue
            sys.stderr.write("ERROR: Aurora setup screen not recognized on %s\n" % serial)
            return False

        if "anonymous@gmail.com" in ui and "Manage your account" in ui:
            cancel = center_for_attr(ui, "content-desc", "Cancel")
            if cancel:
                tap(serial, cancel)
            else:
                adb(serial, "input", "keyevent", "KEYCODE_BACK")
            time.sleep(2)
            continue

        allow = dev.parse_button_center(ui, "android:id/button1")
        if "Allow Aurora Store to access Shizuku" in ui and allow:
            tap(serial, allow)
            time.sleep(2)
            continue

        anonymous = center_for_attr(ui, "resource-id", "com.aurora.store:id/btn_anonymous")
        if anonymous:
            print("Tapped Aurora Anonymous on %s." % serial)
            tap(serial, anonymous)
            time.sleep(5)
            continue

        for label in ("Skip", "OK", "Continue"):
            point = center_for_attr(ui, "text", label)
            if point:
                print("Tapped Aurora %s on %s." % (label, serial))
                tap(serial, point)
                time.sleep(2)
                break
        else:
            sys.stderr.write("ERROR: Aurora setup screen not recognized on %s\n" % serial)
            return False

    sys.stderr.write("ERROR: Aurora setup did not reach home screen on %s\n" % serial)
    return False


def wait_for_text(serial, text, timeout=10):
    if _HS is not None:
        if _HS.wait_text(text, timeout_ms=int(timeout * 1000)):
            return _HS.ui()
        return _HS.ui()
    deadline = time.time() + timeout
    while time.time() < deadline:
        ui_xml = dump_xml(serial)
        if 'text="%s"' % saxutils.escape(text, {'"': "&quot;"}) in ui_xml:
            return ui_xml
        time.sleep(1)
    return dump_xml(serial)


def tap_text(serial, text, timeout=10):
    if _HS is not None:
        if not _HS.wait_text(text, timeout_ms=int(timeout * 1000)):
            sys.stderr.write("ERROR: could not find Aurora text %r on %s\n" % (text, serial))
            return False
        if not _HS.tap_text(text, timeout_ms=4000):
            sys.stderr.write("ERROR: could not tap Aurora text %r on %s\n" % (text, serial))
            return False
        time.sleep(2)
        return True
    ui_xml = wait_for_text(serial, text, timeout)
    point = center_for_attr(ui_xml, "text", text)
    if not point:
        sys.stderr.write("ERROR: could not find Aurora text %r on %s\n" % (text, serial))
        return False
    tap(serial, point)
    time.sleep(2)
    return True


def open_settings(serial):
    if _HS is not None:
        ui = _HS.ui()
        if "aurora.store" not in ui.lower() and "Apps" not in ui:
            open_aurora(serial)
        if not (
            _HS.tap_id("com.aurora.store:id/menu_more", timeout_ms=2500)
            or _HS.tap_desc("More", timeout_ms=2000)
        ):
            sys.stderr.write("ERROR: could not find Aurora More button on %s\n" % serial)
            return False
        time.sleep(2)
        return tap_text(serial, "Settings")

    ui_xml = dump_xml(serial)
    if 'package="com.aurora.store"' not in ui_xml:
        open_aurora(serial)
        ui_xml = dump_xml(serial)
    more = center_for_attr(ui_xml, "resource-id", "com.aurora.store:id/menu_more")
    if not more:
        more = center_for_attr(ui_xml, "content-desc", "More")
    if not more:
        sys.stderr.write("ERROR: could not find Aurora More button on %s\n" % serial)
        return False
    tap(serial, more)
    time.sleep(2)
    return tap_text(serial, "Settings")


def approve_shizuku_dialog(serial):
    ui = _ui_text(serial)
    if "Allow Aurora Store to access Shizuku" not in ui:
        return
    if _HS is not None:
        _HS.tap_text("Allow", timeout_ms=2000)
        time.sleep(2)
        return
    allow = dev.parse_button_center(ui, "android:id/button1")
    if allow:
        tap(serial, allow)
        time.sleep(2)


def configure_installer(serial):
    if not open_settings(serial):
        return False
    if not tap_text(serial, "Installation"):
        return False
    if not tap_text(serial, "Installation method"):
        return False
    if not tap_text(serial, "Shizuku installer"):
        return False
    approve_shizuku_dialog(serial)
    ui = _ui_text(serial)
    if _HS is not None:
        checked, ok = _HS.switch_near_label("Shizuku installer", timeout_ms=3000)
        if not (ok and checked) and "Shizuku installer" not in ui:
            sys.stderr.write("ERROR: Aurora Shizuku installer was not selected on %s\n" % serial)
            return False
        # Accept if label present after tap (some builds omit Switch checked in ui table).
        if "Shizuku installer" not in ui:
            sys.stderr.write("ERROR: Aurora Shizuku installer was not selected on %s\n" % serial)
            return False
    elif "Shizuku installer" not in ui or 'checked="true"' not in ui:
        sys.stderr.write("ERROR: Aurora Shizuku installer was not selected on %s\n" % serial)
        return False
    print("Aurora Store installer set to Shizuku on %s." % serial)
    return True


def configure_auto_updates(serial):
    # Return to the Settings category list from Installation method.
    for _ in range(3):
        ui = _ui_text(serial)
        if "Settings" in ui and "Updates" in ui:
            break
        adb(serial, "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
    else:
        if not open_settings(serial):
            return False

    if not tap_text(serial, "Updates"):
        return False
    if not tap_text(serial, "Automatic updates"):
        return False
    if not tap_text(serial, "Check & install available updates automatically"):
        return False
    print("Aurora Store automatic updates enabled on %s." % serial)
    return True


def configure_update_filters(serial):
    """Limit update checks to apps Aurora installed; also drop F-Droid packages."""
    # Stay on / return to Updates settings screen.
    for _ in range(3):
        ui = _ui_text(serial)
        if any(l in ui for l in FILTER_AURORA_ONLY_LABELS + FILTER_FDROID_LABELS):
            break
        if "Settings" in ui and "Updates" in ui:
            if not tap_text(serial, "Updates"):
                return False
            break
        adb(serial, "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
    else:
        if not open_settings(serial):
            return False
        if not tap_text(serial, "Updates"):
            return False

    if not ensure_preference_on(
        serial, FILTER_AURORA_ONLY_LABELS, "filter apps from other sources"
    ):
        return False
    if not ensure_preference_on(serial, FILTER_FDROID_LABELS, "filter F-Droid apps"):
        return False

    # Optional WorkManager restrictions — fail soft if submenu missing or
    # OS/WorkManager refuses the switch (common when battery is optimized).
    ui = _ui_text(serial)
    if "Automatic updates restrictions" in ui:
        if tap_text(serial, "Automatic updates restrictions", timeout=6):
            for label in AUTO_UPDATE_RESTRICTION_LABELS:
                ensure_preference_on(
                    serial,
                    (label,),
                    "auto-update restriction %s" % label,
                    required=False,
                )
    return True


def main_mac_adb(host):
    """Mac-side ScreenControlSession via resolve_adb (USB or wireless)."""
    global _SHELL, _HS
    serial = dev.resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    try:
        with sc.ScreenControlSession(host, label=host) as session:
            _SHELL = session.shell
            with uid.try_handsets(serial, host) as hs:
                _HS = hs
                ensure_battery_optimized(serial)
                open_aurora(serial)
                dismiss_background_run_dialog(serial)
                if not finish_first_run(serial):
                    return 1
                if not configure_installer(serial):
                    return 1
                if not configure_auto_updates(serial):
                    return 1
                if not configure_update_filters(serial):
                    return 1
                # Prior screen restored by ScreenControlSession.__exit__.
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _SHELL = None
        _HS = None
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: configure_aurora.py <p7a|s24|hd8|serial>\n")
        return 2

    host = argv[0]
    return remote.run_with_mac_fallback(
        host,
        "stayturgid_configure_aurora.py",
        [],
        lambda: main_mac_adb(host),
    )


if __name__ == "__main__":
    sys.exit(main())
