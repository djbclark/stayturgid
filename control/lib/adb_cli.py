"""Shared Mac adb helpers for stayturgid CLI scripts."""
from __future__ import annotations

import subprocess
import sys
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
