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


def _dump_activities(serial: str) -> str:
    result = adb(serial, "shell", "dumpsys", "activity", "activities", check=False)
    return (result.stdout or "") + (result.stderr or "")


def debugging_dialog_present(serial: str) -> bool:
    """Detect (never interact with) the 'Allow USB/wireless debugging?' dialog.

    This is a per-network/per-key human consent gate — Android does not let
    it be granted programmatically, and it only needs a human's own tap
    once per network. A prior version of this function tried to accept it
    via blind keyevent sequences (checkbox + Allow), guessing at dialog
    layout across OEM variants. That automation raced with an actual human
    trying to tap the real dialog: fleet_health_monitor.py calls this check
    unconditionally on every health-check pass, and a keyevent-based retry
    firing mid-tap reset the dialog and cancelled the human's in-progress
    interaction (confirmed live on hd8, 2026-07-31 — see issue #43).

    Returns True if the dialog is currently showing, so the caller can
    notify a human to go tap it themselves instead.
    """
    text = _dump_activities(serial)
    return "UsbDebuggingActivity" in text or "WifiDebuggingActivity" in text


def dismiss_app_compatibility_dialog(serial: str) -> bool:
    """Dismiss the 'Android App Compatibility' 16 KB alignment dialog.

    Android 16 shows this for debuggable apps with unaligned native libraries.
    The dialog has [OK] and [Don't Show Again] buttons. Returns True if found
    and dismissed.
    """
    text = _dump_activities(serial)
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
