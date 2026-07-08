#!/usr/bin/env python3
"""Enable AutoJs6 Shizuku access without manual drawer toggling.

Deterministic order:
  1. grant_shizuku.py — pm grant + shizuku.json (privileged shell, no UI)
  2. Launch AutoJs6 + dismiss notification / Shizuku permission dialogs
  3. Open drawer, scroll to "Shizuku access", enable switch when off
  4. Verify drawer switch ON (optional shizuku-probe.js log when RunIntent works)

Usage: ./enable_autojs6_shizuku.py <s24|p7a|hd8|serial>
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
DRAWER_LABEL = "Shizuku access"
PROBE_REMOTE = "/sdcard/stayturgid/autojs6/scripts/shizuku-probe.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
GRANT = Path(__file__).resolve().parent / "grant_shizuku.py"
DRAWER_SCROLL_ROUNDS = 8

PERM_DIALOG_MARKERS = (
    "Allow org.autojs.autojs6 to access Shizuku",
    "Allow AutoJs6 to access Shizuku",
    "access Shizuku",
    "Grant AutoJs6 access in Shizuku",
)


def adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
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


def launch_autojs6(serial: str) -> None:
    adb(serial, "am", "force-stop", AUTOJS_PKG)
    time.sleep(1)
    adb(serial, "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.5)
    result = adb(serial, "monkey", "-p", AUTOJS_PKG, "-c", "android.intent.category.LAUNCHER", "1")
    if result.returncode != 0:
        adb(serial, "am", "start", "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER", "-p", AUTOJS_PKG)
    time.sleep(3)


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


def find_drawer_switch(serial: str, label: str) -> tuple[bool, int, int] | None:
    """Return (checked, cx, cy) for label's switch, opening/scrolling the drawer as needed."""
    xml = dump_xml(serial)
    sw = dev.parse_switch(xml, label)
    if sw is not None:
        return sw
    open_drawer(serial)
    for attempt in range(DRAWER_SCROLL_ROUNDS):
        xml = dump_xml(serial)
        sw = dev.parse_switch(xml, label)
        if sw is not None:
            return sw
        if attempt < DRAWER_SCROLL_ROUNDS - 1:
            scroll_drawer_down(serial)
            time.sleep(0.8)
    return None


def enable_drawer_shizuku(serial: str) -> bool:
    sw = find_drawer_switch(serial, DRAWER_LABEL)
    if not sw:
        sys.stderr.write("ERROR: Shizuku access row not found in AutoJs6 drawer\n")
        return False
    if sw[0]:
        print("AutoJs6 drawer: Shizuku access already ON.")
        return True
    print("Tapping Shizuku access drawer switch...")
    tap(serial, (sw[1], sw[2]))
    time.sleep(2)
    dismiss_dialogs(serial)
    sw2 = find_drawer_switch(serial, DRAWER_LABEL)
    if sw2 and sw2[0]:
        print("AutoJs6 drawer: Shizuku access ON.")
        return True
    sys.stderr.write("ERROR: Shizuku access switch still OFF after tap\n")
    return False


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


def verify_drawer_enabled(serial: str) -> bool:
    sw = find_drawer_switch(serial, DRAWER_LABEL)
    if not sw:
        print("Verify: Shizuku access row not found")
        return False
    if not sw[0]:
        print("Verify: Shizuku access drawer switch OFF")
        return False
    if not pm_shizuku_granted(serial):
        print("WARN: drawer ON but pm grant not visible in dumpsys yet")
    return True


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: enable_autojs6_shizuku.py <s24|p7a|hd8|serial>\n")
        return 2

    alias = argv[0]
    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    if sync_shizuku_grants(alias) != 0:
        sys.stderr.write("ERROR: grant_shizuku failed\n")
        return 1
    if not shizuku_server_running(serial):
        sys.stderr.write("ERROR: shizuku_server not running — start Shizuku first\n")
        return 1
    if not pm_shizuku_granted(serial):
        print("WARN: pm grant not visible yet — UI flow may still grant it")

    try:
        with sc.ScreenControlSession(alias, label=alias):
            launch_autojs6(serial)
            dismiss_dialogs(serial)

            if verify_drawer_enabled(serial):
                run_shizuku_probe(serial)
                adb(serial, "input", "keyevent", "KEYCODE_HOME")
                print("Shizuku access enabled for AutoJs6 on %s." % alias)
                return 0

            dismiss_dialogs(serial)
            if not enable_drawer_shizuku(serial):
                return 1
            dismiss_dialogs(serial)

            if verify_drawer_enabled(serial):
                run_shizuku_probe(serial)
                adb(serial, "input", "keyevent", "KEYCODE_HOME")
                print("Shizuku access enabled for AutoJs6 on %s." % alias)
                return 0

            sys.stderr.write("ERROR: Shizuku access drawer still OFF on %s\n" % alias)
            return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
