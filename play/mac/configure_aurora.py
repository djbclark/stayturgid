#!/usr/bin/env python3
"""Finish Aurora Store first-run setup from the Mac.

Usage: ./play/mac/configure_aurora.py <s24|hd8|p7a|serial>

Skips the intro carousel, selects Aurora's anonymous session, and configures the
installer/update settings needed for unattended installs. Called automatically at
the end of ./mac/deploy-fleet.sh and ./mac/deploy-play.sh.
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

AURORA_PKG = "com.aurora.store"


def adb(serial, *args, timeout=30):
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


def finish_first_run(serial):
    for _ in range(12):
        xml = dump_xml(serial)
        if 'resource-id="com.aurora.store:id/nav_view"' in xml and 'text="Apps"' in xml:
            print("Aurora Store first-run setup already complete on %s." % serial)
            return True
        if "anonymous@gmail.com" in xml and "Manage your account" in xml:
            cancel = center_for_attr(xml, "content-desc", "Cancel")
            if cancel:
                tap(serial, cancel)
            else:
                adb(serial, "input", "keyevent", "KEYCODE_BACK")
            time.sleep(2)
            continue

        allow = dev.parse_button_center(xml, "android:id/button1")
        if "Allow Aurora Store to access Shizuku" in xml and allow:
            tap(serial, allow)
            time.sleep(2)
            continue

        anonymous = center_for_attr(xml, "resource-id", "com.aurora.store:id/btn_anonymous")
        if anonymous:
            print("Tapped Aurora Anonymous on %s." % serial)
            tap(serial, anonymous)
            time.sleep(5)
            continue

        for label in ("Skip", "OK", "Continue"):
            point = center_for_attr(xml, "text", label)
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
    deadline = time.time() + timeout
    while time.time() < deadline:
        ui_xml = dump_xml(serial)
        if 'text="%s"' % saxutils.escape(text, {'"': "&quot;"}) in ui_xml:
            return ui_xml
        time.sleep(1)
    return dump_xml(serial)


def tap_text(serial, text, timeout=10):
    ui_xml = wait_for_text(serial, text, timeout)
    point = center_for_attr(ui_xml, "text", text)
    if not point:
        sys.stderr.write("ERROR: could not find Aurora text %r on %s\n" % (text, serial))
        return False
    tap(serial, point)
    time.sleep(2)
    return True


def open_settings(serial):
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
    ui_xml = dump_xml(serial)
    if "Allow Aurora Store to access Shizuku" not in ui_xml:
        return
    allow = dev.parse_button_center(ui_xml, "android:id/button1")
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
    ui_xml = dump_xml(serial)
    if "Shizuku installer" not in ui_xml or 'checked="true"' not in ui_xml:
        sys.stderr.write("ERROR: Aurora Shizuku installer was not selected on %s\n" % serial)
        return False
    print("Aurora Store installer set to Shizuku on %s." % serial)
    return True


def configure_auto_updates(serial):
    # Return to the Settings category list from Installation method.
    for _ in range(3):
        ui_xml = dump_xml(serial)
        if 'text="Settings"' in ui_xml and 'text="Updates"' in ui_xml:
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


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: configure_aurora.py <p7a|s24|hd8|serial>\n")
        return 2

    host = argv[0]
    serial = dev.resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    try:
        with sc.ScreenControlSession(host, label=host):
            open_aurora(serial)
            if not finish_first_run(serial):
                return 1
            if not configure_installer(serial):
                return 1
            if not configure_auto_updates(serial):
                return 1
            adb(serial, "input", "keyevent", "KEYCODE_HOME")
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
