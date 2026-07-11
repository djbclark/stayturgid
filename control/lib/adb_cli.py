"""Shared Mac adb helpers for stayturgid CLI scripts."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT / "control" / "lib") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))

import stayturgid_device as dev  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
AUTOJS_PROJECT_BASE = "/sdcard/stayturgid/autojs6"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "LogLevel=ERROR"]


def resolve_target(alias: str) -> str:
    return dev.resolve_adb(alias)


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


def start_autojs_file(serial: str, remote_path: str, *, force_stop: bool = False) -> None:
    """Start an AutoJs6 script via RunIntentActivity only (never termux-open).

    Bare ``file://`` VIEW without the AutoJs6 component can surface Termux's
    "Save file in ~/downloads/" dialog (seen on Fire when heal used the wrong
    open path).  Explicit ``-n`` + ``--user 0`` keeps the intent on AutoJs6.

    ``force_stop=True`` adds ``-S`` (force-stop before start) — needed on
    Fire OS where AutoJs6 can get stuck and ``am start`` delivers the intent
    to the zombie without running the script.
    """
    # Prefer content URI under external storage when path is under /sdcard.
    data = f"file://{remote_path}"
    cmd = ["shell", "am", "start", "--user", "0"]
    if force_stop:
        cmd.append("-S")
    cmd.extend([
        "-a", "android.intent.action.VIEW",
        "-d", data,
        "-t", "application/x-javascript",
        "-n", f"{AUTOJS_PKG}/{AUTOJS_RUN}",
    ])
    adb(serial, *cmd, check=False)


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


def authorize_fleet_adb_key(serial: str) -> bool:
    """Pre-authorize the fleet ADB key on device (Option 1).

    Pushes the fleet ADB public key into /data/misc/adb/adb_keys so the
    'Allow USB debugging?' dialog never appears for this key. Requires
    a privileged shell (uid 2000) on the device.

    The key is authorized for both USB and wireless debugging.
    """
    key_path = Path.home() / ".config" / "stayturgid" / "adbkey.pub"
    if not key_path.is_file():
        print("WARN: fleet ADB key not found at %s" % key_path, file=sys.stderr)
        return False
    pub_key = key_path.read_text(encoding="utf-8").strip()
    if not pub_key:
        return False

    result = run(
        ["adb", "-s", serial, "shell",
         "echo", "%s" % pub_key, ">>", "/data/misc/adb/adb_keys"],
        check=False,
    )
    if result.returncode == 0:
        print("Fleet ADB key authorized on %s." % serial)
        return True
    print("WARN: could not authorize fleet ADB key (rc=%d)" % result.returncode, file=sys.stderr)
    return False


def dismiss_usb_debugging_dialog(serial: str) -> bool:
    """Dismiss the 'Allow USB debugging?' dialog (Option 2).

    Uses key events to check 'Always allow from this computer' and tap
    'Allow'. No uiautomator or Handsets needed — pure input keyevents.

    Returns True if the dialog was found and dismissed.
    """
    result = run(
        ["adb", "-s", serial, "shell", "dumpsys", "window", "windows"],
        check=False,
    )
    text = (result.stdout or "") + (result.stderr or "")
    if "Allow USB debugging" not in text and "allow USB debugging" not in text.lower():
        return False

    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_TAB"], check=False)
    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_SPACE"], check=False)
    time.sleep(0.3)
    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_TAB"], check=False)
    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_ENTER"], check=False)
    print("Dismissed 'Allow USB debugging?' dialog on %s." % serial)
    return True
