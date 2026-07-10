"""Navigate Google Play Store to Auto-update apps (Handsets, no ScreenControlSession).

Play Store account-drawer navigation is brittle under display inversion; callers
that only need a verification screenshot should use this module without
``ScreenControlSession``. See docs/vlm.md.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui_driver import HandsetsSession

PLAY_PKG = "com.android.vending"
PLAY_ACTIVITY = "com.android.vending/.AssetBrowserActivity"


def launch_play_store(serial: str) -> None:
    subprocess.run(
        ["adb", "-s", serial, "shell", "am", "start", "-n", PLAY_ACTIVITY],
        capture_output=True,
        timeout=30,
    )


def _open_account_menu(hs: HandsetsSession) -> bool:
    if hs.tap_any_text(
        "Signed in as Daniel Clark",
        "Signed in as",
        "djbclark@gmail.com",
        timeout_ms=4000,
    ):
        return True
    ui = hs.ui()
    if "Manage apps & device" in ui:
        return True
    # Landscape Fire Play Store: profile chip top-right (~1238,63 in hs coords).
    if hs.hs("tap", "1238", "63", "--timeout", "2000").returncode == 0:
        time.sleep(0.8)
        return hs.wait_text("Manage apps & device", timeout_ms=4000)
    return False


def open_autoupdate_screen(hs: HandsetsSession, serial: str) -> bool:
    """Open Play Store → account → Settings → Network → Auto-update apps."""
    # No ScreenControlSession here (inversion breaks Play drawer); still pin
    # portrait so Fire/phone coords match Handsets assumptions.
    try:
        import screen_control as sc  # noqa: WPS433 — optional fleet dep

        sc.apply_portrait_lock(serial)
    except Exception:  # noqa: BLE001
        pass
    launch_play_store(serial)
    time.sleep(1.5)
    for _ in range(2):
        hs.hs("go", "back", "--timeout", "1500")
        time.sleep(0.4)
    if not _open_account_menu(hs):
        return False
    if not hs.wait_text("Manage apps & device", timeout_ms=5000):
        return False
    time.sleep(0.5)
    hs.hs("swipe", "up")
    time.sleep(0.5)
    if hs.hs("wait", "Settings", "--timeout", "3000").returncode != 0:
        return False
    if hs.hs("tap", "Settings", "--timeout", "4000", "--visible").returncode != 0:
        return False
    time.sleep(1.0)
    if not hs.tap_any_text("Network preferences", "Network Preferences", timeout_ms=4000):
        return False
    time.sleep(0.8)
    if not hs.tap_any_text("Auto-update apps", "Auto-update Apps", timeout_ms=4000):
        return False
    time.sleep(0.8)
    return hs.find_text("auto-update") or hs.find_text("Don't auto-update") or hs.find_text(
        "Over Wi-Fi"
    )


def capture_autoupdate_screenshot(serial: str, dest: Path, hs: HandsetsSession) -> Path | None:
    if not open_autoupdate_screen(hs, serial):
        return None
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        subprocess.run(
            ["adb", "-s", serial, "exec-out", "screencap", "-p"],
            check=True,
            stdout=f,
            timeout=60,
        )
    return dest
