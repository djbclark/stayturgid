#!/usr/bin/env python3
"""Import Obtainium catalog — SSH on-device UI with Mac adb fallback.

s24/p7a: prefer SSH → stayturgid_import_catalog.py; on failure use Mac adb.
hd8 / raw serial: Mac adb only (Fire OS has no Termux localhost:5555).

Usage:
  ./import_catalog.py <p7a|s24|hd8|serial> [all|autojs6|/path/to.json]
  ./import_catalog.py <host> all --force
"""
from __future__ import print_function

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import xml.sax.saxutils as saxutils

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402
import post_ui_remote as remote  # noqa: E402
import ui_driver as uid  # noqa: E402

# Optional Handsets session for Mac path (set in main_mac_adb).
_HS = None

OBTAINIUM_PKG = "dev.imranr.obtainium"
CATALOGS = {
    "all": os.path.join(REPO, "catalogs", "obtainium", "stayturgid-apps.json"),
    "autojs6": os.path.join(REPO, "catalogs", "obtainium", "autojs6-only.json"),
}
IMPORT_DIALOG_TITLE = "Import apps"
CONTINUE_LABEL = "Continue"
CANARY_APPS = {
    "all": ["AutoJs6", "Aurora Store", "Termux", "Shizuku (thedjchi)"],
    "autojs6": ["AutoJs6"],
}


def load_catalog(path):
    with open(path) as f:
        data = json.load(f)
    apps = data.get("apps")
    if not apps:
        raise ValueError("catalog has no apps: %s" % path)
    return apps


def build_import_uri(apps):
    encoded = urllib.parse.quote(json.dumps(apps, separators=(",", ":")))
    return "obtainium://apps/" + encoded


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


def import_dialog_visible(ui_xml):
    xml = ui_xml or ""
    return IMPORT_DIALOG_TITLE in xml or CONTINUE_LABEL in xml


def continue_button(ui_xml):
    return center_for_attr(ui_xml, "content-desc", CONTINUE_LABEL)


def tracking_label(name):
    return name.split("(")[0].strip()


def app_visible(ui_xml, name):
    xml = ui_xml or ""
    if name in xml:
        return True
    label = tracking_label(name)
    if label and label in xml:
        return True
    return re.search(
        r'content-desc="' + re.escape(label) + r'(?:&#10;|")',
        xml,
    ) is not None


def catalog_tracked(ui_xml, app_names):
    return all(app_visible(ui_xml, name) for name in app_names)


def _screen_text(serial):
    if _HS is not None:
        return _HS.ui()
    return dump_xml(serial)


def adb_shell(serial, *args, timeout=30):
    try:
        return subprocess.run(
            ["adb", "-s", serial, "shell"] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def dump_xml(serial, path="/sdcard/obtainium_import.xml", retries=3):
    for attempt in range(retries):
        adb_shell(serial, "uiautomator", "dump", path)
        result = adb_shell(serial, "cat", path)
        xml = result.stdout.replace("\r", "") if result else ""
        if xml and "<hierarchy" in xml:
            return xml
        time.sleep(0.8 + attempt)
    return ""


def tap(serial, point, shell=None):
    runner = shell or (lambda *args, **kw: adb_shell(serial, *args, **kw))
    runner("input", "tap", str(point[0]), str(point[1]))


def wake(serial, shell=None):
    runner = shell or (lambda *args, **kw: adb_shell(serial, *args, **kw))
    runner("input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(0.5)


def scroll_app_list(serial, height_hint=2200, shell=None):
    if _HS is not None:
        _HS.swipe("up")
        time.sleep(0.6)
        return
    runner = shell or (lambda *args, **kw: adb_shell(serial, *args, **kw))
    mid_x = 400
    runner("input", "swipe", str(mid_x), str(int(height_hint * 0.72)),
            str(mid_x), str(int(height_hint * 0.22)), "350")
    time.sleep(0.6)


def tracked_with_scroll(serial, app_names, passes=4, shell=None):
    xml = _screen_text(serial)
    dismiss_blocking_dialogs(serial, xml, shell=shell)
    xml = _screen_text(serial)
    if catalog_tracked(xml, app_names):
        return True
    for _ in range(passes):
        scroll_app_list(serial, shell=shell)
        xml = _screen_text(serial)
        dismiss_blocking_dialogs(serial, xml, shell=shell)
        xml = _screen_text(serial)
        if catalog_tracked(xml, app_names):
            return True
    return False


def dismiss_snackbar(serial, ui_xml, shell=None):
    if _HS is not None:
        if _HS.tap_desc("Dismiss", timeout_ms=800):
            time.sleep(0.3)
        return
    point = center_for_attr(ui_xml, "content-desc", "Dismiss")
    if point:
        tap(serial, point, shell=shell)
        time.sleep(0.3)


def dismiss_blocking_dialogs(serial, ui_xml, shell=None):
    dismiss_snackbar(serial, ui_xml, shell=shell)
    if _HS is not None:
        hit = _HS.tap_any_text("Okay", "OK", "Ok", timeout_ms=800)
        if hit:
            time.sleep(0.5)
            return True
        if _HS.tap_desc("Okay", timeout_ms=600) or _HS.tap_desc("OK", timeout_ms=600):
            time.sleep(0.5)
            return True
        return False
    for label in ("Okay", "OK", "Ok"):
        point = center_for_attr(ui_xml, "content-desc", label)
        if point:
            tap(serial, point, shell=shell)
            time.sleep(0.5)
            return True
    return False


def canary_names(which, catalog_path, apps):
    if which in CANARY_APPS:
        return CANARY_APPS[which]
    if catalog_path == CATALOGS.get("all"):
        return CANARY_APPS["all"]
    if catalog_path == CATALOGS.get("autojs6"):
        return CANARY_APPS["autojs6"]
    return [a.get("name") or a["id"] for a in apps[:3]]


def confirm_import(serial, timeout=12, shell=None):
    for _ in range(timeout):
        xml = _screen_text(serial)
        dismiss_blocking_dialogs(serial, xml, shell=shell)
        if not import_dialog_visible(xml):
            time.sleep(0.4)
            continue
        if _HS is not None:
            if _HS.tap_desc("Continue", timeout_ms=2000) or _HS.tap_text(
                "Continue", timeout_ms=2000
            ):
                time.sleep(2)
                xml = _screen_text(serial)
                dismiss_blocking_dialogs(serial, xml, shell=shell)
                return True
            time.sleep(0.4)
            continue
        point = continue_button(xml)
        if not point:
            time.sleep(0.4)
            continue
        tap(serial, point, shell=shell)
        time.sleep(2)
        xml = _screen_text(serial)
        dismiss_blocking_dialogs(serial, xml, shell=shell)
        return True
    return False


def launch_import_uri(serial, uri, shell=None):
    wake(serial, shell=shell)
    runner = shell or (lambda *args, **kw: adb_shell(serial, *args, **kw))
    runner("am", "start", "-a", "android.intent.action.VIEW", "-d", uri)
    time.sleep(2)


def import_catalog(serial, catalog_path, which="all", force=False, shell=None):
    apps = load_catalog(catalog_path)
    names = [a.get("name") or a["id"] for a in apps]
    canaries = canary_names(which, catalog_path, apps)

    wake(serial, shell=shell)
    runner = shell or (lambda *args, **kw: adb_shell(serial, *args, **kw))
    runner("am", "start", "-n", "%s/.MainActivity" % OBTAINIUM_PKG)
    time.sleep(2)
    if not force and tracked_with_scroll(serial, canaries, passes=3, shell=shell):
        print("Obtainium catalog already tracked on %s (%d apps)." % (serial, len(names)))
        return True

    uri = build_import_uri(apps)
    launch_import_uri(serial, uri, shell=shell)
    if not confirm_import(serial, shell=shell):
        sys.stderr.write("ERROR: Obtainium import dialog not confirmed on %s\n" % serial)
        return False

    if tracked_with_scroll(serial, canaries, passes=5, shell=shell):
        print("Imported %d apps into Obtainium on %s." % (len(names), serial))
        return True

    missing = [n for n in canaries if not app_visible(_screen_text(serial), n)]
    sys.stderr.write(
        "ERROR: import finished but catalog canaries missing in Obtainium UI: %s\n"
        % ", ".join(missing)
    )
    return False


def resolve_catalog(which):
    if which in CATALOGS:
        return CATALOGS[which]
    if os.path.isfile(which):
        return which
    raise ValueError("unknown catalog %r (use all, autojs6, or a .json path)" % which)


def main_mac_adb(host, which, force):
    """Mac-side ScreenControlSession via resolve_adb (USB or wireless)."""
    global _HS
    serial = dev.resolve_adb(host)
    try:
        catalog_path = resolve_catalog(which)
    except ValueError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 2

    result = adb_shell(serial, "pm", "path", OBTAINIUM_PKG)
    if not result or not (result.stdout or "").strip():
        sys.stderr.write("ERROR: Obtainium not installed on %s\n" % serial)
        return 1

    adb_shell(serial, "wait-for-device")
    try:
        with sc.ScreenControlSession(host, label=host) as session:
            with uid.try_handsets(serial, host) as hs:
                _HS = hs
                if not import_catalog(
                    session.serial, catalog_path, which=which, force=force, shell=session.shell
                ):
                    return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _HS = None
    return 0


# Back-compat alias for callers/tests that still name the Mac path "usb".
main_mac_usb = main_mac_adb


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write(
            "usage: import_catalog.py <p7a|s24|hd8|serial> [all|autojs6|path.json] [--force]\n"
        )
        return 2

    host = argv[0]
    which = "all"
    force = False
    for arg in argv[1:]:
        if arg == "--force":
            force = True
        elif not arg.startswith("-"):
            which = arg

    args = [which]
    if force:
        args.append("--force")
    return remote.run_with_mac_fallback(
        host,
        "stayturgid_import_catalog.py",
        args,
        lambda: main_mac_adb(host, which, force),
    )


if __name__ == "__main__":
    sys.exit(main())
