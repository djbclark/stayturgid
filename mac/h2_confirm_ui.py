#!/usr/bin/env python3
"""H2 eyeball helper: capture Neo Store + Aurora settings screenshots.

PARKED — not run by fleet. Manual use only when re-enabling app stores.

Usage: ./mac/h2_confirm_ui.py [s24|p7a|hd8 ...]

Holds one ScreenControlSession per host (inversion on). Navigates settings
screens and saves PNGs under artifacts/h2-confirm/<host>/.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "mac"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402
import ui_driver as uid  # noqa: E402

OUT = REPO / "artifacts" / "h2-confirm"
NEO = "com.machiav3lli.fdroid"
AURORA = "com.aurora.store"


def adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def shot(serial: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["adb", "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=40,
    )
    path.write_bytes(r.stdout or b"")
    print("  shot", path.name, len(r.stdout or b""), "bytes")


def launch(serial: str, component: str) -> None:
    adb(serial, "am", "force-stop", component.split("/")[0])
    time.sleep(0.5)
    adb(serial, "am", "start", "-n", component)
    time.sleep(2.5)


def confirm_neo(host: str, session, hs, out: Path) -> None:
    serial = session.serial
    print("[%s] Neo Store" % host)
    launch(serial, "%s/.NeoActivity" % NEO)
    shot(serial, out / "01_neo_home.png")
    # Settings gear / overflow — try several labels
    opened = False
    if hs is not None:
        for lab in ("Settings", "Preferencias", "Einstellungen"):
            if hs.tap_desc(lab, timeout_ms=1500) or hs.tap_text(lab, timeout_ms=1500):
                opened = True
                break
        if not opened:
            # often bottom nav or overflow content-desc
            for lab in ("More options", "More", "菜单"):
                if hs.tap_desc(lab, timeout_ms=1200):
                    time.sleep(1)
                    if hs.tap_text("Settings", timeout_ms=2000):
                        opened = True
                        break
    time.sleep(1.5)
    shot(serial, out / "02_neo_settings.png")
    if hs is not None:
        hs.tap_text("Installer", timeout_ms=2500) or hs.tap_text("Installation", timeout_ms=2000)
        time.sleep(1.2)
    shot(serial, out / "03_neo_installer.png")
    # scroll for auto-update row
    session.shell("input", "swipe", "540", "1600", "540", "800")
    time.sleep(1)
    shot(serial, out / "04_neo_settings_scrolled.png")
    # Next step launches Aurora; session exit restores prior screen.


def confirm_aurora(host: str, session, hs, out: Path) -> None:
    serial = session.serial
    print("[%s] Aurora Store" % host)
    launch(serial, "%s/.MainActivity" % AURORA)
    time.sleep(1)
    shot(serial, out / "10_aurora_home.png")
    if hs is not None:
        hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=2500) or hs.tap_desc(
            "More", timeout_ms=2000
        )
        time.sleep(1)
        hs.tap_text("Settings", timeout_ms=2500)
        time.sleep(1.5)
    shot(serial, out / "11_aurora_settings.png")
    if hs is not None:
        hs.tap_text("Installation", timeout_ms=2500)
        time.sleep(1)
        hs.tap_text("Installation method", timeout_ms=2500)
        time.sleep(1.2)
    shot(serial, out / "12_aurora_installer.png")
    # back to settings root
    for _ in range(3):
        session.shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.6)
    if hs is not None:
        # re-open settings if needed
        ui = hs.ui()
        if "Updates" not in ui and "Installation" not in ui:
            hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=2000)
            time.sleep(0.8)
            hs.tap_text("Settings", timeout_ms=2000)
            time.sleep(1)
        hs.tap_text("Updates", timeout_ms=2500)
        time.sleep(1.2)
    shot(serial, out / "13_aurora_updates.png")
    if hs is not None:
        hs.tap_text("Automatic updates", timeout_ms=2500)
        time.sleep(1)
    shot(serial, out / "14_aurora_auto_updates.png")
    session.shell("input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.8)
    shot(serial, out / "15_aurora_updates_filters.png")
    # App battery via system settings
    adb(
        serial,
        "am",
        "start",
        "-a",
        "android.settings.APPLICATION_DETAILS_SETTINGS",
        "-d",
        "package:%s" % AURORA,
    )
    time.sleep(2)
    shot(serial, out / "20_aurora_app_info.png")
    if hs is not None:
        # Pixel / Samsung / Fire labels for battery
        for lab in ("App battery usage", "Battery", "Battery usage", "Power usage"):
            if hs.tap_text(lab, timeout_ms=1800):
                time.sleep(1.2)
                break
        else:
            session.shell("input", "swipe", "540", "1600", "540", "900")
            time.sleep(0.8)
            for lab in ("App battery usage", "Battery", "Battery usage"):
                if hs.tap_text(lab, timeout_ms=1500):
                    time.sleep(1.2)
                    break
    shot(serial, out / "21_aurora_battery.png")
    # Prior screen restored by ScreenControlSession.__exit__.


def confirm_host(host: str) -> Path:
    serial = dev.resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
    out = OUT / host
    out.mkdir(parents=True, exist_ok=True)
    print("=== H2 confirm %s (%s) ===" % (host, serial))
    with sc.ScreenControlSession(host, label=host) as session:
        with uid.try_handsets(serial, host) as hs:
            confirm_neo(host, session, hs, out)
            confirm_aurora(host, session, hs, out)
    print("[%s] done → %s" % (host, out))
    return out


def main(argv: list[str] | None = None) -> int:
    hosts = argv if argv is not None else sys.argv[1:]
    if not hosts:
        hosts = ["s24", "p7a", "hd8"]
    # Never skip presence — inversion required for live UI.
    os.environ.pop("STAYTURGID_SKIP_PRESENCE", None)
    for host in hosts:
        try:
            confirm_host(host)
        except sc.ScreenControlError as e:
            sys.stderr.write("ERROR %s: %s\n" % (host, e))
            return 1
        except Exception as e:
            sys.stderr.write("ERROR %s: %s\n" % (host, e))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
