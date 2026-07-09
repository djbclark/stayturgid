#!/usr/bin/env python3
"""On-device AutoJs6 fleet drawer + Shizuku enable (Termux → localhost:5555).

Usage: stayturgid_enable_autojs6.py
All input events go through ScreenControlSession.shell (inversion-gated).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import stayturgid_shell as sh

sh.ensure_lib_path()
import stayturgid_screen_control as sc  # noqa: E402
import stayturgid_handsets as hs  # noqa: E402
import a11y_services as a11y  # noqa: E402
from ui_parse import (  # noqa: E402
    parse_button_center,
    parse_content_desc_center,
    parse_switch,
    parse_text_center,
)

# Optional Handsets wire session (Termux localhost daemon).
_HS: hs.Session | None = None

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
A11Y_SVC = a11y.AUTOJS6_A11Y
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
DRAWER_A11Y = "Accessibility service"
DRAWER_SHIZUKU = "Shizuku access"
PROBE_REMOTE = "/sdcard/stayturgid/autojs6/scripts/shizuku-probe.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
DRAWER_DEFAULTS = os.path.join(sh.STG, "autojs6_drawer_defaults.json")
if not os.path.isfile(DRAWER_DEFAULTS):
    _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DRAWER_DEFAULTS = os.path.join(_repo, "shared", "autojs6_drawer_defaults.json")
DRAWER_SCROLL_ROUNDS = 8
CRITICAL_DRAWER_ON = frozenset({"Foreground service"})

PERM_DIALOG_MARKERS = (
    "Allow org.autojs.autojs6 to access Shizuku",
    "Allow AutoJs6 to access Shizuku",
    "access Shizuku",
    "Grant AutoJs6 access in Shizuku",
)

A11Y_DIALOG_HINTS = (
    "accessibility",
    "observe your actions",
    "autojs",
    "retrieve window content",
    "perform gestures",
)

# a11y_services.PROFILES_PATH already resolves ~/.stayturgid/a11y_profiles.json
# when deployed on-device — do not overwrite with a str (breaks Path.is_file).


def adb_shell(shell, *args, timeout=30):
    return shell(*args, timeout=timeout)


def dump_xml(shell):
    if _HS is not None:
        # Callers that search XML substrings also work on flattened dump text.
        return _HS.dump_text()
    shell("uiautomator", "dump", "/sdcard/stayturgid_autojs6_ui.xml")
    rc, out = shell("cat", "/sdcard/stayturgid_autojs6_ui.xml")
    return (out or "").replace("\r", "")


def tap(shell, point):
    if _HS is not None:
        _HS.tap_xy(int(point[0]), int(point[1]))
        return
    shell("input", "tap", str(point[0]), str(point[1]))


def screen_size(shell):
    w, h = 1080, 2400
    rc, out = shell("wm", "size")
    for line in (out or "").splitlines():
        if "Physical size:" in line:
            parts = line.split(":")[-1].strip().split("x")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])
    return w, h


def sync_shizuku_grants():
    grant = os.path.join(sh.STG, "bin", "stayturgid_grant_shizuku.py")
    if not os.path.isfile(grant):
        grant = os.path.join(os.path.dirname(__file__), "stayturgid_grant_shizuku.py")
    print("Syncing Shizuku manager grants for AutoJs6...")
    return subprocess.run([sys.executable, grant], cwd=os.path.dirname(grant) or ".").returncode


def shizuku_server_running(shell):
    rc, out = shell("pgrep", "-f", "shizuku_server")
    return rc == 0 and bool((out or "").strip())


def pm_shizuku_granted(shell):
    rc, text = shell("dumpsys", "package", AUTOJS_PKG)
    text = text or ""
    if SHIZUKU_PERM not in text:
        return False
    block = text.split(SHIZUKU_PERM, 1)[-1][:400]
    return "granted=true" in block


def a11y_services_list(shell):
    rc, out = shell("settings", "get", "secure", "enabled_accessibility_services")
    return (out or "").strip()


def a11y_enabled(shell):
    return A11Y_SVC in a11y_services_list(shell)


def put_a11y_services(shell, value):
    shell("settings", "put", "secure", "enabled_accessibility_services", value)
    shell("settings", "put", "secure", "accessibility_enabled", "1")


def enable_a11y_shell_append(shell, alias):
    before = a11y_services_list(shell)
    if A11Y_SVC in before:
        return True
    target = a11y.desired_services(alias, before, ensure_autojs6=True)
    put_a11y_services(shell, target)
    time.sleep(1)
    after = a11y_services_list(shell)
    repair = a11y.repair_after_shrink(before, after, alias)
    if repair and repair != after:
        put_a11y_services(shell, repair)
        time.sleep(1)
        after = a11y_services_list(shell)
    return A11Y_SVC in after


def backup_a11y_services(shell, alias):
    live = a11y_services_list(shell)
    state = os.path.join(os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid"), "state")
    os.makedirs(state, exist_ok=True)
    path = os.path.join(state, "a11y_services_backup.txt")
    with open(path, "w") as f:
        f.write(a11y.normalize_value(live) + "\n")
    return live


def launch_autojs6(shell, *, force_stop=True):
    if force_stop:
        shell("am", "force-stop", AUTOJS_PKG)
        time.sleep(1)
    shell("input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.5)
    rc, _ = shell("monkey", "-p", AUTOJS_PKG, "-c", "android.intent.category.LAUNCHER", "1")
    if rc != 0:
        shell("am", "start", "-a", "android.intent.action.MAIN",
              "-c", "android.intent.category.LAUNCHER", "-p", AUTOJS_PKG)
    time.sleep(3)


def foreground_package(shell):
    rc, out = shell("dumpsys", "activity", "activities")
    for line in (out or "").splitlines():
        if "topResumedActivity" in line and "{" in line:
            chunk = line.split("{", 1)[-1].split("}", 1)[0]
            for part in chunk.split():
                if "/" in part and "." in part:
                    return part.split("/")[0]
    return ""


def return_to_autojs6(shell):
    for _ in range(6):
        if foreground_package(shell) == AUTOJS_PKG:
            return
        shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.6)
    launch_autojs6(shell, force_stop=False)
    dismiss_dialogs(shell)


def _drawer_markers_present(shell) -> bool:
    if _HS is not None:
        return _HS.contains(
            DRAWER_SHIZUKU, DRAWER_A11Y, "Foreground service", "Floating button",
        )
    xml = dump_xml(shell)
    return any(
        label in xml
        for label in (
            DRAWER_SHIZUKU,
            DRAWER_A11Y,
            "Foreground service",
            "Floating button",
        )
    )


def open_drawer(shell):
    if _drawer_markers_present(shell):
        return
    if _HS is not None:
        for desc in ("Open drawer", "Open navigation drawer"):
            if _HS.tap_desc(desc):
                time.sleep(1.2)
                if _drawer_markers_present(shell):
                    return
                if _HS.tap_desc(desc):
                    time.sleep(1.2)
                    if _drawer_markers_present(shell):
                        return
        _HS.swipe("right")
        time.sleep(1.2)
        return
    xml = dump_xml(shell)
    for desc in ("Open drawer", "Open navigation drawer"):
        point = parse_content_desc_center(xml, desc)
        if point:
            tap(shell, point)
            time.sleep(1.5)
            return
    w, h = screen_size(shell)
    shell("input", "swipe", "10", str(h // 2), str(w - 10), str(h // 2), "300")
    time.sleep(1.5)


def scroll_drawer_down(shell):
    if _HS is not None:
        _HS.swipe("up")
        return
    w, h = screen_size(shell)
    x = w // 3
    shell("input", "swipe", str(x), str(int(h * 0.75)), str(x), str(int(h * 0.25)), "400")


def scroll_drawer_up(shell):
    if _HS is not None:
        _HS.swipe("down")
        return
    w, h = screen_size(shell)
    x = w // 3
    shell("input", "swipe", str(x), str(int(h * 0.25)), str(x), str(int(h * 0.75)), "400")


def scroll_drawer_to_top(shell):
    for _ in range(5):
        scroll_drawer_up(shell)
        time.sleep(0.3)


def find_drawer_switch(shell, label, *, reset=True):
    if reset:
        return_to_autojs6(shell)
        open_drawer(shell)
        for _ in range(4):
            scroll_drawer_up(shell)
            time.sleep(0.4)

    if _HS is not None:
        for attempt in range(DRAWER_SCROLL_ROUNDS + 6):
            checked, ok = _HS.switch_near_label(label)
            if ok:
                # Coords unused when tapping via Handsets helpers.
                return (bool(checked), 0, 0)
            if _HS.find_text(label):
                return (False, 0, 0)
            if attempt < DRAWER_SCROLL_ROUNDS + 5:
                scroll_drawer_down(shell)
                time.sleep(0.35)
        return None

    for attempt in range(DRAWER_SCROLL_ROUNDS + 6):
        xml = dump_xml(shell)
        if label in xml:
            sw = parse_switch(xml, label)
            if sw is not None:
                return sw
            time.sleep(0.4)
            xml = dump_xml(shell)
            sw = parse_switch(xml, label)
            if sw is not None:
                return sw
        if attempt < DRAWER_SCROLL_ROUNDS + 5:
            scroll_drawer_down(shell)
            time.sleep(0.55)
    return None


def dismiss_a11y_system_dialogs(shell, rounds=10):
    for _ in range(rounds):
        if _HS is not None:
            ui = _HS.dump_text().lower()
            if not any(hint in ui for hint in A11Y_DIALOG_HINTS):
                break
            acted = False
            hit = _HS.tap_any_text("Allow", "Turn on", "OK", "Start", "Agree")
            if hit:
                print("Tapped accessibility dialog: %s" % hit)
                time.sleep(2)
                acted = True
            if not acted:
                for name in ("AutoJs6", "Use AutoJs6", DRAWER_A11Y):
                    checked, ok = _HS.switch_near_label(name)
                    if ok and not checked:
                        print("Tapped accessibility switch in system UI: %s" % name)
                        _HS.tap_switch_for_label(name)
                        time.sleep(2)
                        acted = True
                        break
            if not acted:
                break
            continue

        xml = dump_xml(shell)
        lower = xml.lower()
        if not any(hint in lower for hint in A11Y_DIALOG_HINTS):
            btn = parse_button_center(xml, "android:id/button1")
            if not (btn and "allow" in lower):
                break
        acted = False
        for label in ("Allow", "Turn on", "OK", "Start", "Agree"):
            pt = parse_text_center(xml, label)
            if pt:
                print("Tapped accessibility dialog: %s" % label)
                tap(shell, pt)
                time.sleep(2)
                acted = True
                break
        if not acted:
            btn = parse_button_center(xml, "android:id/button1")
            if btn:
                print("Tapped accessibility dialog (button1).")
                tap(shell, btn)
                time.sleep(2)
                acted = True
        if not acted:
            for name in ("AutoJs6", "Use AutoJs6", DRAWER_A11Y):
                sw = parse_switch(xml, name)
                if sw and not sw[0]:
                    print("Tapped accessibility switch in system UI: %s" % name)
                    tap(shell, (sw[1], sw[2]))
                    time.sleep(2)
                    acted = True
                    break
        if not acted:
            break


def dismiss_dialogs(shell, rounds=12):
    for _ in range(rounds):
        if _HS is not None:
            ui = _HS.dump_text()
            lower = ui.lower()
            acted = False
            if "notification" in lower and ("allow" in lower or "don" in lower):
                hit = _HS.tap_any_text(
                    "Allow", "Don't allow", "Don\u2019t allow",
                )
                if hit:
                    print("Tapped notification dialog: %s" % hit)
                    time.sleep(1.5)
                    acted = True
            if any(marker in ui for marker in PERM_DIALOG_MARKERS):
                if _HS.tap_text("Allow"):
                    print("Tapped Shizuku permission Allow.")
                    time.sleep(2)
                    acted = True
            if ("shizuku" in lower or "permission" in lower) and _HS.tap_text("Continue"):
                time.sleep(1)
                acted = True
            if not acted:
                break
            continue

        xml = dump_xml(shell)
        lower = xml.lower()
        acted = False
        if "notification" in lower and ("allow" in lower or "don" in lower):
            for label in ("Allow", "Don't allow", "Don\u2019t allow"):
                pt = parse_text_center(xml, label)
                if pt:
                    print("Tapped notification dialog: %s" % label)
                    tap(shell, pt)
                    time.sleep(1.5)
                    acted = True
                    break
        if any(marker in xml for marker in PERM_DIALOG_MARKERS):
            btn = parse_button_center(xml, "android:id/button1")
            if btn:
                print("Tapped Shizuku permission Allow.")
                tap(shell, btn)
                time.sleep(2)
                acted = True
            else:
                allow = parse_text_center(xml, "Allow")
                if allow:
                    print("Tapped Shizuku Allow (text).")
                    tap(shell, allow)
                    time.sleep(2)
                    acted = True
        cont = parse_text_center(xml, "Continue")
        if cont and ("shizuku" in lower or "permission" in lower):
            tap(shell, cont)
            time.sleep(1)
            acted = True
        if not acted:
            break


def enable_drawer_switch(shell, label):
    result = ensure_drawer_switch(shell, label, True)
    if result == "missing":
        sys.stderr.write("ERROR: %s row not found in AutoJs6 drawer\n" % label)
    return result == "ok"


def ensure_drawer_switch(shell, label, want_on):
    sw = find_drawer_switch(shell, label)
    if sw is None:
        return "missing"
    if sw[0] == want_on:
        state = "ON" if want_on else "OFF"
        print("AutoJs6 drawer: %s already %s." % (label, state))
        return "ok"
    print("Setting drawer %s -> %s..." % (label, "ON" if want_on else "OFF"))
    if _HS is not None:
        if not _HS.tap_switch_for_label(label):
            if (sw[1], sw[2]) != (0, 0):
                tap(shell, (sw[1], sw[2]))
            else:
                return "failed"
    else:
        tap(shell, (sw[1], sw[2]))
    time.sleep(2)
    dismiss_dialogs(shell)
    if label == DRAWER_A11Y:
        dismiss_a11y_system_dialogs(shell)
    return_to_autojs6(shell)
    sw2 = find_drawer_switch(shell, label)
    if sw2 and sw2[0] == want_on:
        return "ok"
    if _HS is not None and sw2 is not None and want_on:
        return "ok"
    return "failed"


def load_drawer_defaults():
    if not os.path.isfile(DRAWER_DEFAULTS):
        return {"on": [], "off": [], "skip_labels": []}
    with open(DRAWER_DEFAULTS) as f:
        return json.load(f)


def apply_drawer_defaults(shell):
    data = load_drawer_defaults()
    skip = set(data.get("skip_labels") or []) | {DRAWER_A11Y, DRAWER_SHIZUKU}
    failures = []
    return_to_autojs6(shell)
    open_drawer(shell)
    scroll_drawer_to_top(shell)
    items = []
    for label in data.get("on") or []:
        if label not in skip:
            items.append((label, True))
    for label in data.get("off") or []:
        if label not in skip:
            items.append((label, False))
    for label, want_on in items:
        scroll_drawer_to_top(shell)
        sw = find_drawer_switch(shell, label, reset=False)
        if sw is None:
            if label in CRITICAL_DRAWER_ON:
                failures.append("%s (missing)" % label)
            else:
                print("WARN: drawer row not found (skipped): %s" % label)
            continue
        if sw[0] == want_on:
            state = "ON" if want_on else "OFF"
            print("AutoJs6 drawer: %s already %s." % (label, state))
            continue
        print("Setting drawer %s -> %s..." % (label, "ON" if want_on else "OFF"))
        if _HS is not None:
            if not _HS.tap_switch_for_label(label):
                if (sw[1], sw[2]) != (0, 0):
                    tap(shell, (sw[1], sw[2]))
                else:
                    failures.append("%s (want %s)" % (label, "ON" if want_on else "OFF"))
                    continue
        else:
            tap(shell, (sw[1], sw[2]))
        time.sleep(2)
        dismiss_dialogs(shell)
        return_to_autojs6(shell)
        open_drawer(shell)
        scroll_drawer_to_top(shell)
        sw2 = find_drawer_switch(shell, label, reset=False)
        if not sw2 or sw2[0] != want_on:
            failures.append("%s (want %s)" % (label, "ON" if want_on else "OFF"))
    return failures


def drawer_switch_states(shell):
    states = {}
    data = load_drawer_defaults()
    labels = set(data.get("on") or []) | set(data.get("off") or [])
    labels.update((DRAWER_A11Y, DRAWER_SHIZUKU))
    return_to_autojs6(shell)
    open_drawer(shell)
    scroll_drawer_to_top(shell)
    for label in sorted(labels):
        sw = find_drawer_switch(shell, label, reset=False)
        if sw is None:
            states[label] = "missing"
        else:
            states[label] = "ON" if sw[0] else "OFF"
    return states


def enable_accessibility(shell, alias):
    before = backup_a11y_services(shell, alias)
    if a11y_enabled(shell):
        print("AutoJs6 accessibility already enabled (settings).")
        return True
    if enable_a11y_shell_append(shell, alias):
        print("AutoJs6 accessibility enabled via settings merge (append-safe).")
        return_to_autojs6(shell)
        return True
    lost = a11y.services_lost(before, a11y_services_list(shell))
    if lost:
        sys.stderr.write(
            "ERROR: accessibility list shrank (%s)\n" % ", ".join(lost)
        )
    sys.stderr.write("ERROR: AutoJs6 accessibility still disabled after settings merge\n")
    return False


def verify_shizuku_drawer(shell):
    """Confirm Shizuku access is ON (same find path as enable_drawer_switch)."""
    # reset=True: return to AutoJs6, open drawer, scroll from top — required
    # because open_drawer while already open can toggle the drawer closed.
    sw = find_drawer_switch(shell, DRAWER_SHIZUKU, reset=True)
    if not sw:
        print("Verify: Shizuku access row not found")
        return False
    if not sw[0]:
        print("Verify: Shizuku access drawer switch OFF")
        return False
    if not pm_shizuku_granted(shell):
        print("WARN: drawer ON but pm grant not visible in dumpsys yet")
    print("Verify: Shizuku access drawer switch ON")
    return True


def run_shizuku_probe(shell):
    shell("am", "start",
          "-a", "android.intent.action.VIEW",
          "-d", "file://" + PROBE_REMOTE,
          "-t", "text/javascript",
          "-n", "%s/%s" % (AUTOJS_PKG, AUTOJS_RUN))
    time.sleep(4)
    rc, out = shell("tail", "-12", WATCHDOG_LOG)
    lines = [ln for ln in (out or "").splitlines() if "[setup] shizuku" in ln]
    text = lines[-1] if lines else ""
    print("Probe: %s" % (text or "(no log line)"))
    return "operational=true" in text.lower()


def report_debug_state(shell, alias):
    sys.stderr.write("\n=== AutoJs6 enable FAILED on %s — debug bundle ===\n" % alias)
    sys.stderr.write("enabled_accessibility_services:\n  %s\n" % a11y_services_list(shell))
    _rc, aen = shell("settings", "get", "secure", "accessibility_enabled")
    sys.stderr.write("accessibility_enabled: %s\n" % (aen or "").strip())
    sys.stderr.write("shizuku_server: %s\n" % ("up" if shizuku_server_running(shell) else "down"))
    sys.stderr.write("pm shizuku grant visible: %s\n" % pm_shizuku_granted(shell))
    sys.stderr.write("foreground package: %s\n" % foreground_package(shell))
    for label, state in drawer_switch_states(shell).items():
        sys.stderr.write("drawer %s: %s\n" % (label, state))
    sys.stderr.write("=== end debug bundle ===\n")


def main(argv=None):
    global _HS
    argv = argv if argv is not None else sys.argv[1:]
    alias = argv[0] if argv else (sh.read_device_profile().get("alias") or "device")

    if sync_shizuku_grants() != 0:
        sys.stderr.write("ERROR: grant_shizuku failed\n")
        return 1

    try:
        with sc.ScreenControlSession(label=alias) as session:
            shell = session.shell
            with hs.try_session() as handsets:
                _HS = handsets
                if not shizuku_server_running(shell):
                    sys.stderr.write(
                        "ERROR: shizuku_server not running — start Shizuku first\n"
                    )
                    return 1
                launch_autojs6(shell)
                dismiss_dialogs(shell)
                if not enable_accessibility(shell, alias):
                    report_debug_state(shell, alias)
                    return 1
                return_to_autojs6(shell)
                drawer_failures = apply_drawer_defaults(shell)
                critical = [
                    f for f in drawer_failures if any(c in f for c in CRITICAL_DRAWER_ON)
                ]
                if critical:
                    sys.stderr.write(
                        "ERROR: critical drawer settings failed: %s\n"
                        % ", ".join(critical)
                    )
                    report_debug_state(shell, alias)
                    return 1
                if drawer_failures:
                    print(
                        "WARN: non-critical drawer settings: %s"
                        % ", ".join(drawer_failures)
                    )
                if verify_shizuku_drawer(shell) and a11y_enabled(shell):
                    run_shizuku_probe(shell)
                    shell("input", "keyevent", "KEYCODE_HOME")
                    print("AutoJs6 fleet drawer + Shizuku enabled on %s." % alias)
                    return 0
                if not enable_drawer_switch(shell, DRAWER_SHIZUKU):
                    report_debug_state(shell, alias)
                    return 1
                dismiss_dialogs(shell)
                if verify_shizuku_drawer(shell) and a11y_enabled(shell):
                    run_shizuku_probe(shell)
                    shell("input", "keyevent", "KEYCODE_HOME")
                    print("AutoJs6 fleet drawer + Shizuku enabled on %s." % alias)
                    return 0
                report_debug_state(shell, alias)
                return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    finally:
        _HS = None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
