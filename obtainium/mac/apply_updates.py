#!/usr/bin/env python3
"""Open Obtainium and drive the bulk "Install/update apps" flow.

Python replacement for apply-updates.sh — the installer-dialog button parsing
is now the unit-tested shared/mac/stayturgid_device.parse_button_center()
instead of `tr '>' '\n' | grep | sed`.

Usage: ./apply_updates.py <p7a|s24|serial>
Requires: unlocked screen, Obtainium in foreground. Confirms package-installer
dialogs (taps android:id/button2 — the positive action on Samsung One UI;
unverified on Pixel, where button1 may be positive).
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
BULK = (476, 2017)
CONTINUE = (727, 1433)
PLAY_PROTECT_DISMISS = (540, 1629)


def installer_action(xml):
    """Classify the current screen from a uiautomator dump. Returns one of:
      ("installer", (cx, cy))  -- package installer up; tap button2 center
      ("playprotect", None)    -- Play Protect blocked the install
      (None, None)             -- nothing to do
    Pure — the tap-decision logic, unit-tested without a device."""
    xml = xml or ""
    if 'package="com.google.android.packageinstaller"' in xml:
        center = dev.parse_button_center(xml, "android:id/button2")
        return ("installer", center)
    if 'package="com.android.vending"' in xml:
        return ("playprotect", None)
    return (None, None)


def adb_shell(serial, *args):
    try:
        return subprocess.run(["adb", "-s", serial, "shell"] + list(args),
                              capture_output=True, text=True)
    except OSError:
        return None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: apply_updates.py <p7a|s24|serial>\n")
        return 2
    serial = dev.resolve_adb(argv[0])

    adb_shell(serial, "am", "start", "-n", "%s/.MainActivity" % OBTAINIUM_PKG)
    time.sleep(3)
    adb_shell(serial, "input", "tap", str(BULK[0]), str(BULK[1]))
    time.sleep(2)
    adb_shell(serial, "input", "tap", str(CONTINUE[0]), str(CONTINUE[1]))
    print("Tapped bulk update + Continue — handling installer dialogs for ~90s...")

    for _ in range(18):
        time.sleep(5)
        adb_shell(serial, "uiautomator", "dump", "/sdcard/obtainium_apply.xml")
        r = adb_shell(serial, "cat", "/sdcard/obtainium_apply.xml")
        xml = r.stdout if r else ""
        kind, center = installer_action(xml)
        if kind == "installer" and center:
            adb_shell(serial, "input", "tap", str(center[0]), str(center[1]))
            print("  confirmed package installer (button2)")
        elif kind == "playprotect":
            print("  WARN: Play Protect dialog — dismiss manually or disable "
                  "verifier (HACKING.md)")
            adb_shell(serial, "input", "tap", str(PLAY_PROTECT_DISMISS[0]),
                      str(PLAY_PROTECT_DISMISS[1]))

    print("Done. Re-check Obtainium app list for any remaining Update badges.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
