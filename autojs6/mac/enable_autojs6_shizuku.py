#!/usr/bin/env python3
"""Enable AutoJs6 fleet drawer defaults without manual toggling.

Deterministic order:
  1. grant_shizuku.py — pm grant + shizuku.json (privileged shell, no UI)
  2. Launch AutoJs6 + dismiss notification / permission dialogs
  3. Accessibility ON (drawer + shell append fallback)
  4. Fleet drawer profile from shared/autojs6_drawer_defaults.json (UI)
  5. Shizuku access ON + verify; debug bundle on failure

Usage: ./enable_autojs6_shizuku.py <s24|p7a|hd8|serial>
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import a11y_services as a11y  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402
import post_ui_remote as remote  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
A11Y_SVC = a11y.AUTOJS6_A11Y
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
DRAWER_A11Y = "Accessibility service"
DRAWER_SHIZUKU = "Shizuku access"
PROBE_REMOTE = "/sdcard/stayturgid/autojs6/scripts/shizuku-probe.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
GRANT = Path(__file__).resolve().parent / "grant_shizuku.py"
DRAWER_DEFAULTS = REPO_ROOT / "shared" / "autojs6_drawer_defaults.json"
DRAWER_SCROLL_ROUNDS = 8
CRITICAL_DRAWER_ON = frozenset({"Foreground service"})

# Bound inside ScreenControlSession so input is inversion-gated.
_SHELL = None

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


def a11y_append_value(current: str, svc: str = A11Y_SVC) -> str:
    """Append-only enabled_accessibility_services value (never replace the list)."""
    return a11y.append_service(current, svc)


def backup_a11y_services(serial: str, alias: str) -> str:
    live = a11y_services_list(serial)
    a11y.write_backup_file(a11y.backup_file_for(alias), live)
    tmp = REPO_ROOT / "shared" / "a11y_backups" / (".push_%s.tmp" % alias)
    a11y.write_backup_file(tmp, live)
    adb(serial, "mkdir", "-p", "/sdcard/stayturgid/state")
    subprocess.run(
        ["adb", "-s", serial, "push", str(tmp), "/sdcard/stayturgid/%s" % a11y.DEVICE_BACKUP_REL],
        capture_output=True,
        check=False,
    )
    tmp.unlink(missing_ok=True)
    return live


def adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    if _SHELL is not None:
        rc, out = _SHELL(*args, timeout=timeout)

        class _R:
            returncode = rc
            stdout = out

        return _R()  # type: ignore[return-value]
    return subprocess.run(
        ["adb", "-s", serial, "shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def dump_xml(serial: str) -> str:
    adb(serial, "uiautomator", "dump", "/sdcard/stayturgid_autojs6_ui.xml")
    result = adb(serial, "cat", "/sdcard/stayturgid_autojs6_ui.xml")
    return (result.stdout or "").replace("\r", "")


def tap(serial: str, point: tuple[int, int]) -> None:
    adb(serial, "input", "tap", str(point[0]), str(point[1]))


def screen_size(serial: str) -> tuple[int, int]:
    w, h = 1080, 2400
    size = adb(serial, "wm", "size")
    for line in (size.stdout or "").splitlines():
        if "Physical size:" in line:
            parts = line.split(":")[-1].strip().split("x")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])
    return w, h


def sync_shizuku_grants(alias: str) -> int:
    if not GRANT.is_file():
        print("WARN: grant_shizuku.py missing", file=sys.stderr)
        return 0
    print("Syncing Shizuku manager grants for AutoJs6...")
    return subprocess.run([sys.executable, str(GRANT), alias], cwd=REPO_ROOT).returncode


def shizuku_server_running(serial: str) -> bool:
    result = adb(serial, "pgrep", "-f", "shizuku_server")
    return result.returncode == 0 and bool((result.stdout or "").strip())


def pm_shizuku_granted(serial: str) -> bool:
    result = adb(serial, "dumpsys", "package", AUTOJS_PKG)
    text = result.stdout or ""
    if SHIZUKU_PERM not in text:
        return False
    block = text.split(SHIZUKU_PERM, 1)[-1][:400]
    return "granted=true" in block


def a11y_services_list(serial: str) -> str:
    result = adb(serial, "settings", "get", "secure", "enabled_accessibility_services")
    return (result.stdout or "").strip()


def a11y_enabled(serial: str) -> bool:
    return A11Y_SVC in a11y_services_list(serial)


def put_a11y_services(serial: str, value: str) -> None:
    adb(serial, "settings", "put", "secure", "enabled_accessibility_services", value)
    adb(serial, "settings", "put", "secure", "accessibility_enabled", "1")


def enable_a11y_shell_append(serial: str, alias: str) -> bool:
    before = a11y_services_list(serial)
    if A11Y_SVC in before:
        return True
    target = a11y.desired_services(alias, before, ensure_autojs6=True)
    put_a11y_services(serial, target)
    time.sleep(1)
    after = a11y_services_list(serial)
    repair = a11y.repair_after_shrink(before, after, alias)
    if repair and repair != after:
        put_a11y_services(serial, repair)
        time.sleep(1)
        after = a11y_services_list(serial)
    return A11Y_SVC in after


def launch_autojs6(serial: str, *, force_stop: bool = True) -> None:
    if force_stop:
        adb(serial, "am", "force-stop", AUTOJS_PKG)
        time.sleep(1)
    adb(serial, "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.5)
    result = adb(serial, "monkey", "-p", AUTOJS_PKG, "-c", "android.intent.category.LAUNCHER", "1")
    if result.returncode != 0:
        adb(serial, "am", "start", "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER", "-p", AUTOJS_PKG)
    time.sleep(3)


def foreground_package(serial: str) -> str:
    result = adb(serial, "dumpsys", "activity", "activities")
    for line in (result.stdout or "").splitlines():
        if "topResumedActivity" in line and "{" in line:
            chunk = line.split("{", 1)[-1].split("}", 1)[0]
            parts = chunk.split()
            for part in parts:
                if "/" in part and "." in part:
                    return part.split("/")[0]
    return ""


def return_to_autojs6(serial: str) -> None:
    """Leave Settings/consent UIs and bring AutoJs6 main activity to foreground."""
    for _ in range(6):
        if foreground_package(serial) == AUTOJS_PKG:
            return
        adb(serial, "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.6)
    launch_autojs6(serial, force_stop=False)
    dismiss_dialogs(serial)


def open_drawer(serial: str) -> None:
    xml = dump_xml(serial)
    for desc in ("Open drawer", "Open navigation drawer"):
        point = dev.parse_content_desc_center(xml, desc)
        if point:
            tap(serial, point)
            time.sleep(1.5)
            return
    w, h = screen_size(serial)
    adb(serial, "input", "swipe", "10", str(h // 2), str(w - 10), str(h // 2), "300")
    time.sleep(1.5)


def scroll_drawer_down(serial: str) -> None:
    w, h = screen_size(serial)
    x = w // 3
    adb(serial, "input", "swipe", str(x), str(int(h * 0.75)), str(x), str(int(h * 0.25)), "400")


def scroll_drawer_up(serial: str) -> None:
    w, h = screen_size(serial)
    x = w // 3
    adb(serial, "input", "swipe", str(x), str(int(h * 0.25)), str(x), str(int(h * 0.75)), "400")


def scroll_drawer_to_top(serial: str) -> None:
    for _ in range(5):
        scroll_drawer_up(serial)
        time.sleep(0.3)


def find_drawer_switch(
    serial: str, label: str, *, reset: bool = True,
) -> tuple[bool, int, int] | None:
    if reset:
        return_to_autojs6(serial)
        open_drawer(serial)
        for _ in range(4):
            scroll_drawer_up(serial)
            time.sleep(0.4)
    for attempt in range(DRAWER_SCROLL_ROUNDS + 4):
        xml = dump_xml(serial)
        sw = dev.parse_switch(xml, label)
        if sw is not None:
            return sw
        if attempt < DRAWER_SCROLL_ROUNDS + 3:
            scroll_drawer_down(serial)
            time.sleep(0.5)
    return None


def dismiss_a11y_system_dialogs(serial: str, rounds: int = 10) -> None:
    for _ in range(rounds):
        xml = dump_xml(serial)
        lower = xml.lower()
        if not any(hint in lower for hint in A11Y_DIALOG_HINTS):
            btn = dev.parse_button_center(xml, "android:id/button1")
            if not (btn and "allow" in lower):
                break
        acted = False
        for label in ("Allow", "Turn on", "OK", "Start", "Agree"):
            pt = dev.parse_text_center(xml, label)
            if pt:
                print("Tapped accessibility dialog: %s" % label)
                tap(serial, pt)
                time.sleep(2)
                acted = True
                break
        if not acted:
            btn = dev.parse_button_center(xml, "android:id/button1")
            if btn:
                print("Tapped accessibility dialog (button1).")
                tap(serial, btn)
                time.sleep(2)
                acted = True
        if not acted:
            for name in ("AutoJs6", "Use AutoJs6", DRAWER_A11Y):
                sw = dev.parse_switch(xml, name)
                if sw and not sw[0]:
                    print("Tapped accessibility switch in system UI: %s" % name)
                    tap(serial, (sw[1], sw[2]))
                    time.sleep(2)
                    acted = True
                    break
        if not acted:
            break


def dismiss_dialogs(serial: str, rounds: int = 12) -> None:
    for _ in range(rounds):
        xml = dump_xml(serial)
        lower = xml.lower()
        acted = False

        if "notification" in lower and ("allow" in lower or "don" in lower):
            for label in ("Allow", "Don't allow", "Don\u2019t allow"):
                pt = dev.parse_text_center(xml, label)
                if pt:
                    print("Tapped notification dialog: %s" % label)
                    tap(serial, pt)
                    time.sleep(1.5)
                    acted = True
                    break

        if any(marker in xml for marker in PERM_DIALOG_MARKERS):
            btn = dev.parse_button_center(xml, "android:id/button1")
            if btn:
                print("Tapped Shizuku permission Allow.")
                tap(serial, btn)
                time.sleep(2)
                acted = True
            else:
                allow = dev.parse_text_center(xml, "Allow")
                if allow:
                    print("Tapped Shizuku Allow (text).")
                    tap(serial, allow)
                    time.sleep(2)
                    acted = True

        cont = dev.parse_text_center(xml, "Continue")
        if cont and ("shizuku" in lower or "permission" in lower):
            tap(serial, cont)
            time.sleep(1)
            acted = True

        if not acted:
            break


def enable_drawer_switch(serial: str, label: str) -> bool:
    result = ensure_drawer_switch(serial, label, True)
    if result == "missing":
        sys.stderr.write("ERROR: %s row not found in AutoJs6 drawer\n" % label)
    return result == "ok"


def ensure_drawer_switch(serial: str, label: str, want_on: bool) -> str:
    """Set drawer switch to want_on. Returns ok | missing | failed."""
    sw = find_drawer_switch(serial, label)
    if sw is None:
        return "missing"
    if sw[0] == want_on:
        state = "ON" if want_on else "OFF"
        print("AutoJs6 drawer: %s already %s." % (label, state))
        return "ok"
    print("Setting drawer %s -> %s..." % (label, "ON" if want_on else "OFF"))
    tap(serial, (sw[1], sw[2]))
    time.sleep(2)
    dismiss_dialogs(serial)
    if label == DRAWER_A11Y:
        dismiss_a11y_system_dialogs(serial)
    return_to_autojs6(serial)
    sw2 = find_drawer_switch(serial, label)
    if sw2 and sw2[0] == want_on:
        return "ok"
    return "failed"


def load_drawer_defaults() -> dict:
    if not DRAWER_DEFAULTS.is_file():
        return {"on": [], "off": [], "skip_labels": []}
    return json.loads(DRAWER_DEFAULTS.read_text())


def apply_drawer_defaults(serial: str) -> list[str]:
    """Apply shared/autojs6_drawer_defaults.json via drawer UI. Returns failure labels."""
    data = load_drawer_defaults()
    skip = set(data.get("skip_labels") or []) | {DRAWER_A11Y, DRAWER_SHIZUKU}
    failures: list[str] = []
    return_to_autojs6(serial)
    open_drawer(serial)
    scroll_drawer_to_top(serial)
    items: list[tuple[str, bool]] = []
    # ON before OFF — Foreground service lives near top of drawer.
    for label in data.get("on") or []:
        if label not in skip:
            items.append((label, True))
    for label in data.get("off") or []:
        if label not in skip:
            items.append((label, False))
    for label, want_on in items:
        scroll_drawer_to_top(serial)
        sw = find_drawer_switch(serial, label, reset=False)
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
        tap(serial, (sw[1], sw[2]))
        time.sleep(2)
        dismiss_dialogs(serial)
        return_to_autojs6(serial)
        open_drawer(serial)
        scroll_drawer_to_top(serial)
        sw2 = find_drawer_switch(serial, label, reset=False)
        if not sw2 or sw2[0] != want_on:
            failures.append("%s (want %s)" % (label, "ON" if want_on else "OFF"))
    return failures


def drawer_switch_states(serial: str) -> dict[str, str]:
    states: dict[str, str] = {}
    data = load_drawer_defaults()
    labels = set(data.get("on") or []) | set(data.get("off") or [])
    labels.update((DRAWER_A11Y, DRAWER_SHIZUKU))
    return_to_autojs6(serial)
    open_drawer(serial)
    scroll_drawer_to_top(serial)
    for label in sorted(labels):
        sw = find_drawer_switch(serial, label, reset=False)
        if sw is None:
            states[label] = "missing"
        else:
            states[label] = "ON" if sw[0] else "OFF"
    return states


def enable_accessibility(serial: str, alias: str) -> bool:
    before = backup_a11y_services(serial, alias)
    if a11y_enabled(serial):
        print("AutoJs6 accessibility already enabled (settings).")
        return True
    # Shell merge only — AutoJs6 drawer toggle REPLACES the entire a11y list.
    if enable_a11y_shell_append(serial, alias):
        print("AutoJs6 accessibility enabled via settings merge (append-safe).")
        return_to_autojs6(serial)
        return True
    lost = a11y.services_lost(before, a11y_services_list(serial))
    if lost:
        sys.stderr.write(
            "ERROR: accessibility list shrank (%s) — run ./mac/a11y_services.py restore %s\n"
            % (", ".join(lost), alias)
        )
    sys.stderr.write("ERROR: AutoJs6 accessibility still disabled after settings merge\n")
    return False


def verify_shizuku_drawer(serial: str) -> bool:
    sw = find_drawer_switch(serial, DRAWER_SHIZUKU)
    if not sw:
        print("Verify: Shizuku access row not found")
        return False
    if not sw[0]:
        print("Verify: Shizuku access drawer switch OFF")
        return False
    if not pm_shizuku_granted(serial):
        print("WARN: drawer ON but pm grant not visible in dumpsys yet")
    return True


def run_shizuku_probe(serial: str) -> bool:
    adb(serial, "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", "file://" + PROBE_REMOTE,
        "-t", "text/javascript",
        "-n", "%s/%s" % (AUTOJS_PKG, AUTOJS_RUN))
    time.sleep(4)
    result = adb(serial, "tail", "-12", WATCHDOG_LOG)
    lines = [ln for ln in (result.stdout or "").splitlines() if "[setup] shizuku" in ln]
    text = lines[-1] if lines else ""
    print("Probe: %s" % (text or "(no log line)"))
    return "operational=true" in text.lower()


def report_debug_state(serial: str, alias: str) -> None:
    sys.stderr.write("\n=== AutoJs6 enable FAILED on %s — debug bundle ===\n" % alias)
    sys.stderr.write("Host: %s  adb: %s\n" % (alias, serial))
    sys.stderr.write("enabled_accessibility_services:\n  %s\n" % a11y_services_list(serial))
    sys.stderr.write("accessibility_enabled: %s\n" % (
        (adb(serial, "settings", "get", "secure", "accessibility_enabled").stdout or "").strip()
    ))
    sys.stderr.write("shizuku_server: %s\n" % ("up" if shizuku_server_running(serial) else "down"))
    sys.stderr.write("pm shizuku grant visible: %s\n" % pm_shizuku_granted(serial))
    sys.stderr.write("foreground package: %s\n" % foreground_package(serial))
    for label, state in drawer_switch_states(serial).items():
        sys.stderr.write("drawer %s: %s\n" % (label, state))
    sys.stderr.write("drawer defaults file: %s\n" % DRAWER_DEFAULTS)
    sys.stderr.write("Re-run: ./autojs6/mac/enable_autojs6_shizuku.py %s\n" % alias)
    sys.stderr.write("Ensure: screen unlocked, Shizuku running, AutoJs6 installed.\n")
    sys.stderr.write("=== end debug bundle ===\n")


def main(argv: list[str] | None = None) -> int:
    global _SHELL
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: enable_autojs6_shizuku.py <s24|p7a|hd8|serial>\n")
        return 2

    alias = argv[0]
    if remote.host_uses_on_device_ui(alias):
        return remote.ssh_run_on_device(alias, "stayturgid_enable_autojs6.py", [alias])

    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    if sync_shizuku_grants(alias) != 0:
        sys.stderr.write("ERROR: grant_shizuku failed\n")
        return 1
    if not shizuku_server_running(serial):
        sys.stderr.write("ERROR: shizuku_server not running — start Shizuku first\n")
        return 1

    try:
        with sc.ScreenControlSession(alias, label=alias) as session:
            _SHELL = session.shell
            launch_autojs6(serial)
            dismiss_dialogs(serial)

            if not enable_accessibility(serial, alias):
                report_debug_state(serial, alias)
                return 1

            return_to_autojs6(serial)

            drawer_failures = apply_drawer_defaults(serial)
            critical = [f for f in drawer_failures
                        if any(c in f for c in CRITICAL_DRAWER_ON)]
            if critical:
                sys.stderr.write("ERROR: critical drawer settings failed: %s\n" % ", ".join(critical))
                report_debug_state(serial, alias)
                return 1
            if drawer_failures:
                print("WARN: non-critical drawer settings: %s" % ", ".join(drawer_failures))

            if verify_shizuku_drawer(serial) and a11y_enabled(serial):
                run_shizuku_probe(serial)
                adb(serial, "input", "keyevent", "KEYCODE_HOME")
                print("AutoJs6 fleet drawer + Shizuku enabled on %s." % alias)
                return 0

            if not enable_drawer_switch(serial, DRAWER_SHIZUKU):
                report_debug_state(serial, alias)
                return 1
            dismiss_dialogs(serial)

            if verify_shizuku_drawer(serial) and a11y_enabled(serial):
                run_shizuku_probe(serial)
                adb(serial, "input", "keyevent", "KEYCODE_HOME")
                print("AutoJs6 fleet drawer + Shizuku enabled on %s." % alias)
                return 0

            report_debug_state(serial, alias)
            return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        report_debug_state(serial, alias)
        return 1
    finally:
        _SHELL = None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
