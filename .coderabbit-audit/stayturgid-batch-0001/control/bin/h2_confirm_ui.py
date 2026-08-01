#!/usr/bin/env python3
"""H2 eyeball helper: capture Neo Store settings screenshots.

PARKED — not run by fleet. Manual use only when re-enabling app stores.

Usage: ./control/bin/h2_confirm_ui.py [oneui-device|stock-android-device|fireos-device ...]

Holds one ScreenControlSession per host (inversion on). Navigates settings
screens and saves PNGs under artifacts/h2-confirm/<host>/.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import screen_control as sc
import stayturgid_device as dev
import ui_driver as uid

OUT = REPO / "artifacts" / "h2-confirm"
NEO = "com.machiav3lli.fdroid"


def adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [dev.adb_bin(), "-s", serial, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def shot(serial: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [dev.adb_bin(), "-s", serial, "exec-out", "screencap", "-p"],
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


def confirm_host(host: str) -> Path:
    serial = dev.resolve_adb(host)
    subprocess.run([dev.adb_bin(), "connect", serial], capture_output=True, text=True)
    out = OUT / host
    out.mkdir(parents=True, exist_ok=True)
    print("=== H2 confirm %s (%s) ===" % (host, serial))

    import ui_guard

    ui_guard.check_ui_guard(
        host=host,
        action_type="H2-CONFIRM-UI",
        message="Please manually perform the Neo Store UI verification.",
    )

    with sc.ScreenControlSession(host, label=host) as session:
        with uid.try_handsets(serial, host) as hs:
            confirm_neo(host, session, hs, out)
    print("[%s] done → %s" % (host, out))
    return out


def main(argv: list[str] | None = None) -> int:
    hosts = argv if argv is not None else sys.argv[1:]
    if not hosts:
        hosts = ["oneui-device", "stock-android-device", "fireos-device"]
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
