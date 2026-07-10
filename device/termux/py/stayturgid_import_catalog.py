#!/usr/bin/env python3
"""On-device Obtainium catalog import (Termux → Handsets / dump fallback).

Usage (on device): stayturgid_import_catalog.py [all|autojs6|/path.json] [--force]
Mac wrapper: control/tools/obtainium/import_catalog.py <host> …
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import xml.sax.saxutils as saxutils

import stayturgid_shell as sh

sh.ensure_lib_path()
import stayturgid_screen_control as sc  # noqa: E402
import stayturgid_handsets as hs  # noqa: E402
from ui_parse import parse_content_desc_center  # noqa: E402

_HS: hs.Session | None = None

OBTAINIUM_PKG = "dev.imranr.obtainium"
CATALOG_DIR = os.path.join(sh.STG, "catalog")
CATALOGS = {
    "all": os.path.join(CATALOG_DIR, "stayturgid-apps.json"),
    "autojs6": os.path.join(CATALOG_DIR, "autojs6-only.json"),
}
# Repo fallback when developing from checkout (repo root = …/stayturgid)
_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if not os.path.isdir(CATALOG_DIR):
    CATALOGS = {
        "all": os.path.join(_REPO, "catalogs", "obtainium", "stayturgid-apps.json"),
        "autojs6": os.path.join(_REPO, "catalogs", "obtainium", "autojs6-only.json"),
    }

IMPORT_DIALOG_TITLE = "Import apps"
CONTINUE_LABEL = "Continue"
# Must match catalogs/obtainium/stayturgid-apps.json (Aurora is optional, not here).
CANARY_APPS = {
    "all": ["AutoJs6", "Termux", "Shizuku (thedjchi)", "Tailscale"],
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


def import_dialog_visible(ui_xml):
    xml = ui_xml or ""
    return IMPORT_DIALOG_TITLE in xml or CONTINUE_LABEL in xml


def continue_button(ui_xml):
    if _HS is not None:
        return _HS.center_for("content-desc", CONTINUE_LABEL) or _HS.center_for(
            "text", CONTINUE_LABEL
        )
    return center_for_attr(ui_xml, "content-desc", CONTINUE_LABEL)


def tracking_label(name):
    return name.split("(")[0].strip()


def app_visible(ui_xml, name):
    xml = ui_xml or ""
    if name in xml:
        return True
    label = tracking_label(name)
    if label in xml:
        return True
    return re.search(
        r'content-desc="' + re.escape(label) + r'(?:&#10;|")',
        xml,
    ) is not None


def catalog_tracked(ui_xml, app_names):
    return all(app_visible(ui_xml, name) for name in app_names)


def dump_xml(shell, path="/sdcard/obtainium_import.xml", retries=3):
    if _HS is not None:
        return _HS.dump_text()
    for attempt in range(retries):
        shell("uiautomator", "dump", path)
        rc, out = shell("cat", path)
        xml = (out or "").replace("\r", "") if rc == 0 else ""
        if xml and "<hierarchy" in xml:
            return xml
        time.sleep(0.8 + attempt)
    return ""


def tap(shell, point):
    if _HS is not None:
        _HS.tap_xy(int(point[0]), int(point[1]))
        return
    shell("input", "tap", str(point[0]), str(point[1]))


def wake(shell):
    # Prefer shell keyevent — Handsets may not expose WAKEUP as a wire key.
    shell("input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(0.5)


def screen_size(shell, default=(1080, 2200)):
    """Return (width, height) from ``wm size``; fall back to *default*."""
    rc, out = shell("wm", "size")
    if rc == 0 and out:
        # Prefer "Override size" / Physical size: WxH
        for line in (out or "").replace("\r", "").splitlines():
            m = re.search(r"(\d+)\s*x\s*(\d+)", line, re.I)
            if m:
                return int(m.group(1)), int(m.group(2))
    return default


def scroll_app_list(shell, height_hint=None):
    if _HS is not None:
        _HS.swipe("up")
        time.sleep(0.6)
        return
    w, h = screen_size(shell) if height_hint is None else (1080, int(height_hint))
    mid_x = max(1, w // 2)
    shell(
        "input",
        "swipe",
        str(mid_x),
        str(int(h * 0.72)),
        str(mid_x),
        str(int(h * 0.22)),
        "350",
    )
    time.sleep(0.6)


def dismiss_snackbar(shell, ui_xml):
    if _HS is not None:
        if _HS.tap_desc("Dismiss"):
            time.sleep(0.3)
        return
    point = center_for_attr(ui_xml, "content-desc", "Dismiss")
    if point:
        tap(shell, point)
        time.sleep(0.3)


def dismiss_blocking_dialogs(shell, ui_xml):
    dismiss_snackbar(shell, ui_xml)
    if _HS is not None:
        hit = _HS.tap_any_text("Okay", "OK", "Ok")
        if hit:
            time.sleep(0.5)
            return True
        return False
    for label in ("Okay", "OK", "Ok"):
        point = center_for_attr(ui_xml, "content-desc", label)
        if point:
            tap(shell, point)
            time.sleep(0.5)
            return True
    return False


def canary_names(which, catalog_path, apps):
    if which in CANARY_APPS:
        names = list(CANARY_APPS[which])
    elif catalog_path == CATALOGS.get("all"):
        names = list(CANARY_APPS["all"])
    elif catalog_path == CATALOGS.get("autojs6"):
        names = list(CANARY_APPS["autojs6"])
    else:
        names = [a.get("name") or a["id"] for a in apps[:4]]
    catalog_labels = {(a.get("name") or a["id"]) for a in apps}
    catalog_labels |= {tracking_label(n) for n in catalog_labels}
    filtered = [
        n
        for n in names
        if n in catalog_labels or tracking_label(n) in catalog_labels
    ]
    return filtered or names


def confirm_import(shell, timeout=12):
    """Tap Continue until Import dialog is gone (may need multiple taps)."""
    saw_dialog = False
    confirmed = False
    for _ in range(timeout):
        xml = dump_xml(shell)
        dismiss_blocking_dialogs(shell, xml)
        xml = dump_xml(shell)
        if not import_dialog_visible(xml):
            if confirmed or saw_dialog:
                return True
            time.sleep(0.4)
            continue
        saw_dialog = True
        point = continue_button(xml)
        if not point:
            time.sleep(0.4)
            continue
        tap(shell, point)
        confirmed = True
        time.sleep(1.5)
    xml = dump_xml(shell)
    dismiss_blocking_dialogs(shell, xml)
    return confirmed and not import_dialog_visible(dump_xml(shell))


def tracked_with_scroll(shell, app_names, passes=4):
    """Accumulate canary hits across scrolls (large cards never share one dump)."""
    if not app_names:
        return True
    found = set()

    def _note(xml):
        for name in app_names:
            if name not in found and app_visible(xml, name):
                found.add(name)

    xml = dump_xml(shell)
    dismiss_blocking_dialogs(shell, xml)
    xml = dump_xml(shell)
    _note(xml)
    if found.issuperset(app_names):
        return True
    for _ in range(passes):
        scroll_app_list(shell)
        xml = dump_xml(shell)
        dismiss_blocking_dialogs(shell, xml)
        xml = dump_xml(shell)
        _note(xml)
        if found.issuperset(app_names):
            return True
    for _ in range(passes):
        # scroll up (ratio-based when Handsets unavailable — review L1)
        if _HS is not None:
            _HS.swipe("down")
            time.sleep(0.6)
        else:
            w, h = screen_size(shell)
            mid_x = max(1, w // 2)
            shell(
                "input",
                "swipe",
                str(mid_x),
                str(int(h * 0.22)),
                str(mid_x),
                str(int(h * 0.72)),
                "350",
            )
            time.sleep(0.6)
        xml = dump_xml(shell)
        dismiss_blocking_dialogs(shell, xml)
        xml = dump_xml(shell)
        _note(xml)
        if found.issuperset(app_names):
            return True
    return False


def resolve_catalog(which):
    if which in CATALOGS:
        return CATALOGS[which]
    if os.path.isfile(which):
        return which
    raise ValueError("unknown catalog %r (use all, autojs6, or a .json path)" % which)


def import_catalog(shell, catalog_path, which="all", force=False):
    apps = load_catalog(catalog_path)
    names = [a.get("name") or a["id"] for a in apps]
    canaries = canary_names(which, catalog_path, apps)

    wake(shell)
    shell("am", "start", "-n", "%s/.MainActivity" % OBTAINIUM_PKG)
    time.sleep(2)
    if not force and tracked_with_scroll(shell, canaries, passes=3):
        print("Obtainium catalog already tracked (%d apps)." % len(names))
        return True

    uri = build_import_uri(apps)
    wake(shell)
    # Fresh process so a stuck empty Import dialog does not swallow the deep link.
    shell("am", "force-stop", OBTAINIUM_PKG)
    time.sleep(0.5)
    shell("am", "start", "-a", "android.intent.action.VIEW", "-d", uri)
    time.sleep(2.5)
    if not confirm_import(shell):
        sys.stderr.write("ERROR: Obtainium import dialog not confirmed\n")
        return False

    if tracked_with_scroll(shell, canaries, passes=6):
        print("Imported %d apps into Obtainium." % len(names))
        return True

    seen = set()
    xml = dump_xml(shell)
    for n in canaries:
        if app_visible(xml, n):
            seen.add(n)
    for _ in range(6):
        scroll_app_list(shell)
        xml = dump_xml(shell)
        for n in canaries:
            if app_visible(xml, n):
                seen.add(n)
    missing = [n for n in canaries if n not in seen]
    sys.stderr.write(
        "ERROR: import finished but catalog canaries missing: %s\n"
        % ", ".join(missing or canaries)
    )
    return False


def main(argv=None):
    global _HS
    argv = argv if argv is not None else sys.argv[1:]
    which = "all"
    force = False
    for arg in argv:
        if arg == "--force":
            force = True
        elif not arg.startswith("-"):
            which = arg

    try:
        catalog_path = resolve_catalog(which)
    except ValueError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 2

    rc, out = sh.shell("pm", "path", OBTAINIUM_PKG)
    if rc != 0 or not (out or "").strip():
        sys.stderr.write("ERROR: Obtainium not installed\n")
        return 1

    try:
        with sc.ScreenControlSession() as session:
            with hs.try_session() as handsets:
                _HS = handsets
                if not import_catalog(
                    session.shell, catalog_path, which=which, force=force
                ):
                    return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _HS = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
