"""Shared Mac adb helpers for stayturgid CLI scripts."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT / "control" / "lib") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))

import stayturgid_device as dev

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "LogLevel=ERROR"]

_SDCARD_DEFAULT = "/sdcard"


def resolve_external_storage(serial: str) -> str:
    """Return the device's external storage path, or fall back to /sdcard."""
    result = adb(serial, "shell", "echo", "${EXTERNAL_STORAGE:-/sdcard}")
    raw = (result.stdout or _SDCARD_DEFAULT).strip()
    return raw if raw.startswith("/") else _SDCARD_DEFAULT


def is_fire_os(serial: str) -> bool:
    """Heuristic: Fire OS devices show amazon in build characteristics."""
    result = adb(serial, "shell", "getprop", "ro.build.characteristics")
    return "amazon" in (result.stdout or "").lower()


def resolve_target(alias: str) -> str:
    return dev.resolve_adb(alias)


def alias_for_host(host: str) -> str | None:
    return dev.alias_for_host(host)


def resolve_ssh(alias: str) -> str:
    return dev.resolve_ssh_host(alias)


def run(
    cmd: list[str],
    *,
    check: bool = False,
    capture: bool = True,
    text: bool = True,
    timeout: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=text,
        timeout=timeout,
        input=input_text,
    )


def adb_bin() -> str:
    return dev.adb_bin()


def adb_devices() -> str:
    result = run([adb_bin(), "devices"])
    return result.stdout or ""


def adb(serial: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return run([adb_bin(), "-s", serial, *args], **kwargs)


def package_installed(serial: str, package: str) -> bool:
    result = adb(serial, "shell", "pm", "path", package)
    return result.returncode == 0 and "package:" in (result.stdout or "")


def ssh_ok(host: str, *, timeout: int = 5) -> bool:
    if not host:
        return False
    return (
        run(
            ["ssh", *SSH_OPTS, "-o", f"ConnectTimeout={timeout}", host, "true"],
            check=False,
        ).returncode
        == 0
    )


def ssh_run(host: str, script: str, *, timeout: int = 60) -> subprocess.CompletedProcess:
    return run(["ssh", *SSH_OPTS, host, "bash", "-s"], input_text=script, timeout=timeout)


def scp(local: Path, host: str, remote: str) -> None:
    run(["scp", "-q", str(local), f"{host}:{remote}"], check=True)


def dismiss_usb_debugging_dialog(serial: str) -> bool:
    """Dismiss the 'Allow USB debugging?' dialog.

    On Android 11+, /data/misc/adb/adb_keys is not directly writable by
    the shell uid — only adbd can write it after the user confirms the
    dialog. This function checks for the dialog and accepts it via
    keyevents (check 'Always allow' + tap 'Allow').

    Returns True if the dialog was found and dismissed.
    """
    result = run(
        ["adb", "-s", serial, "shell", "dumpsys", "activity", "activities"],
        check=False,
    )
    text = (result.stdout or "") + (result.stderr or "")
    if "UsbDebuggingActivity" not in text and "WifiDebuggingActivity" not in text:
        return False

    # Try multiple focus sequences — the dialog layout varies across Android
    # versions and OEMs (standard, Samsung bottom-sheet, etc.).
    sequences = [
        # Standard: checkbox (1 TAB) → Allow (1 TAB)
        [["KEYCODE_TAB"], ["KEYCODE_SPACE"], ["KEYCODE_TAB"], ["KEYCODE_ENTER"]],
        # Samsung: checkbox (2 TABs) → Allow (1 TAB)
        [["KEYCODE_TAB"], ["KEYCODE_TAB"], ["KEYCODE_SPACE"], ["KEYCODE_TAB"], ["KEYCODE_ENTER"]],
        # Samsung bottom sheet: Cancel(1) → checkbox(2) → Allow(1)
        [["KEYCODE_TAB"], ["KEYCODE_TAB"], ["KEYCODE_TAB"], ["KEYCODE_SPACE"], ["KEYCODE_TAB"], ["KEYCODE_ENTER"]],
    ]
    for seq in sequences:
        for key in seq:
            run(["adb", "-s", serial, "shell", "input", "keyevent", key[0]], check=False)
            time.sleep(0.15)
        time.sleep(0.5)
        # Check if dialog is gone
        check = run(
            ["adb", "-s", serial, "shell", "dumpsys", "activity", "activities"],
            check=False,
        )
        text = (check.stdout or "") + (check.stderr or "")
        if "UsbDebuggingActivity" not in text and "WifiDebuggingActivity" not in text:
            print("Dismissed 'Allow USB debugging?' dialog on %s." % serial)
            return True
        # Reset focus: HOME then re-open the dialog... actually just BACK
        run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_BACK"], check=False)
        time.sleep(0.5)
    print("WARN: could not dismiss USB debugging dialog on %s — try manual." % serial)
    return False


def dismiss_app_compatibility_dialog(serial: str) -> bool:
    """Dismiss the 'Android App Compatibility' 16 KB alignment dialog.

    Android 16 shows this for debuggable apps with unaligned native libraries.
    The dialog has [OK] and [Don't Show Again] buttons. Returns True if found
    and dismissed.
    """
    result = run(
        ["adb", "-s", serial, "shell", "dumpsys", "activity", "activities"],
        check=False,
    )
    text = (result.stdout or "") + (result.stderr or "")
    if "AppCompatibility" not in text and "16 KB" not in text:
        return False

    # Tap OK (default focused) to dismiss. ENTER clicks the focused button.
    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_ENTER"], check=False)
    time.sleep(0.3)
    # Verify it's gone.
    check = run(
        ["adb", "-s", serial, "shell", "dumpsys", "activity", "activities"],
        check=False,
    )
    check_text = (check.stdout or "") + (check.stderr or "")
    if "AppCompatibility" not in check_text and "16 KB" not in check_text:
        print("Dismissed App Compatibility (16 KB) dialog on %s." % serial)
        return True
    return False
