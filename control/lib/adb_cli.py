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

# IdentityAgent=none + IdentitiesOnly=yes: never reach the 1Password agent (Touch ID prompt
# for unrelated keys, e.g. vps-primary, t2e 2026-10-17); bare-IP/localhost targets match no Host block.
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "LogLevel=ERROR", "-o", "IdentityAgent=none", "-o", "IdentitiesOnly=yes"]

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


# adbd logs this when a new key connects while it believes an "Allow debugging?"
# prompt is already up; it raises no new dialog until adbd restarts.
ADB_PROMPT_PENDING_MARKER = "prompt currently pending, skipping"

# Same restart the fleet already issues through rish (start_adb.py,
# stayturgid_repair.py), wrapped in the nohup setsid detach used for on-device
# scripts, so `adb shell` returns before adbd (and this connection) goes away.
# service.adb.tcp.port survives an adbd restart, so the TCP listener is kept.
# SELinux denies ctl.restart to shell on Fire OS (session-2026-07-25-k1-verification.md).
ADBD_RESTART_DETACHED = "nohup setsid sh -c 'sleep 2; setprop ctl.restart adbd' </dev/null >/dev/null 2>&1 &"


def adb_prompt_pending_in(logcat_text: str) -> bool:
    """True if logcat text carries adbd's 'prompt currently pending' line."""
    return ADB_PROMPT_PENDING_MARKER in (logcat_text or "")


def _recent_logcat(serial: str, window_s: int) -> str | None:
    """Last window_s seconds of logcat by the device's own clock, or None if unreadable."""
    script = 'logcat -d -v epoch -t "$(( $(date +%%s) - %d )).0"' % window_s
    result = adb(serial, "shell", script, check=False, timeout=30)
    return (result.stdout or "") if result.returncode == 0 else None


def check_adb_prompt(serial: str, *, restart_adbd: bool = False, window_s: int = 600) -> str:
    """Detect a stuck adb authorization prompt; restart adbd only when asked.

    Stuck means adbd logged ADB_PROMPT_PENDING_MARKER in the last window_s
    seconds while no UsbDebuggingActivity/WifiDebuggingActivity is showing, so
    no new key can be authorized until adbd restarts. By default this only
    prints the recovery hint. With restart_adbd=True it issues
    ADBD_RESTART_DETACHED and nothing else: no activity is started, and it
    refuses while the debugging dialog is showing, since a restart then drops
    the connection a human is about to allow and adb's re-dial raises another.

    Returns "unknown" (logcat unreadable), "ok" (nothing pending), "dialog"
    (the dialog is up: a human must tap it), "stuck" (hint printed),
    "restarted" or "restart-failed". After "restarted" the caller must
    re-`adb connect` a TCP serial.
    """
    text = _recent_logcat(serial, window_s)
    if text is None:
        return "unknown"
    if not adb_prompt_pending_in(text):
        return "ok"
    if debugging_dialog_present(serial):
        print("%s: adb auth prompt pending and the debugging dialog is showing; a human must tap it." % serial)
        return "dialog"
    if not restart_adbd:
        print(
            "%s: adbd says an auth prompt is pending but no debugging dialog is showing (stuck prompt). "
            'Recover with: adb -s %s shell "%s" (Fire OS denies this: toggle USB/Wireless debugging '
            "off and on by hand)." % (serial, serial, ADBD_RESTART_DETACHED)
        )
        return "stuck"
    result = adb(serial, "shell", ADBD_RESTART_DETACHED, check=False, timeout=15)
    if result.returncode != 0:
        print("%s: detached adbd restart did not start (rc=%d)." % (serial, result.returncode))
        return "restart-failed"
    print("%s: stuck adb auth prompt; detached adbd restart issued." % serial)
    return "restarted"


INVERSION_KEY = "accessibility_display_inversion_enabled"


def _inversion_state(serial: str) -> str:
    result = adb(serial, "shell", "settings", "get", "secure", INVERSION_KEY, check=False)
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def app_compatibility_dialog_present(serial: str) -> bool:
    """Detect the 'Android App Compatibility' 16 KB alignment dialog.

    Android 16 shows this for debuggable apps with unaligned native libraries.
    """
    text = _dump_activities(serial)
    return "AppCompatibility" in text or "16 KB" in text


def dismiss_app_compatibility_dialog(serial: str) -> bool:
    """Press OK on the 16 KB alignment dialog, with the display inverted.

    Pressing a key is screen control, so the display is inverted around it (the
    visible "agent has the glass" signal, docs/rules/screen-control-hold.md) and
    nothing is pressed unless inversion reads back on. Returns True if the
    dialog was dismissed; the caller notifies a human either way.
    """
    if not app_compatibility_dialog_present(serial):
        return False
    before = _inversion_state(serial)
    adb(serial, "shell", "settings", "put", "secure", INVERSION_KEY, "1", check=False)
    try:
        if _inversion_state(serial) != "1":
            print("Not pressing OK on %s: display inversion did not turn on." % serial)
            return False
        # Tap OK (default focused) to dismiss. ENTER clicks the focused button.
        adb(serial, "shell", "input", "keyevent", "KEYCODE_ENTER", check=False)
        time.sleep(0.3)
    finally:
        if before != "1":
            adb(serial, "shell", "settings", "put", "secure", INVERSION_KEY, before or "0", check=False)
    if not app_compatibility_dialog_present(serial):
        print("Dismissed App Compatibility (16 KB) dialog on %s." % serial)
        return True
    return False
