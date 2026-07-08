#!/usr/bin/env python3
"""Install AutoJs6, grant Termux bridge perms, deploy project, start repair-bridge.

Usage: ./setup_autojs6.py <serial|s24|hd8|p7a> [device-id]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as adb  # noqa: E402

DL_DIR = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "stayturgid-autojs6"
APK_NAME = "autojs6-v6.7.0-arm64-v8a-62db1ff8.apk"
AUTOJS_PKG = adb.AUTOJS_PKG

MKBIN = "mkdir -p ~/.stayturgid/bin ~/.stayturgid/logs ~/.stayturgid/run ~/.termux/boot\n"
BRIDGE_START = """
chmod +x ~/.stayturgid/bin/stayturgid-repair.sh ~/.stayturgid/bin/repair-bridge.sh \
    ~/.termux/boot/start-repair-bridge.sh ~/.termux/boot/start-autojs6-watchdog.sh 2>/dev/null
pid=$(cat ~/.stayturgid/run/bridge.pid 2>/dev/null)
if [ -n "$pid" ] && [ -d "/proc/$pid" ] && grep -q repair-bridge "/proc/$pid/cmdline" 2>/dev/null; then
    echo "bridge already running (pid $pid)"
else
    nohup ~/.stayturgid/bin/repair-bridge.sh >> ~/.stayturgid/logs/bridge.log 2>&1 &
    echo "bridge started"
fi
"""


def deploy_termux_scripts(alias: str, serial: str) -> str:
    """Deploy repair + bridge via SSH when possible; adb fallback otherwise."""
    ssh_host = adb.resolve_ssh(alias)
    termux = REPO_ROOT / "termux"
    if adb.ssh_ok(ssh_host, timeout=5):
        print(f"Deploying Termux scripts via SSH ({ssh_host})...")
        adb.ssh_run(ssh_host, MKBIN)
        adb.scp(termux / "stayturgid-repair.sh", ssh_host, ".stayturgid/bin/stayturgid-repair.sh")
        adb.scp(termux / "repair-bridge.sh", ssh_host, ".stayturgid/bin/repair-bridge.sh")
        adb.scp(termux / "py" / "stayturgid_repair.py", ssh_host, ".stayturgid/bin/stayturgid_repair.py")
        for boot in ("start-repair-bridge.sh", "start-autojs6-watchdog.sh"):
            src = termux / "boot" / boot
            if src.is_file():
                adb.scp(src, ssh_host, f".termux/boot/{boot}")
        result = adb.ssh_run(ssh_host, BRIDGE_START)
        if result.stdout:
            print(result.stdout.rstrip())
        return ssh_host

    print("SSH unavailable — push repair-bridge via adb to /sdcard for manual Termux deploy")
    adb.adb(serial, "push", str(termux / "repair-bridge.sh"), "/sdcard/Download/repair-bridge.sh", check=False)
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: setup_autojs6.py <serial|s24|hd8|p7a> [device-id]\n")
        return 2
    alias = argv[0]
    device_id = argv[1] if len(argv) > 1 else ""
    serial = adb.resolve_target(alias)
    print(f"=== stayturgid AutoJs6 setup on {serial} ===")

    DL_DIR.mkdir(parents=True, exist_ok=True)
    apk_path = DL_DIR / APK_NAME
    if not apk_path.is_file():
        print("Downloading AutoJs6 v6.7.0...")
        subprocess.run(
            [
                "gh",
                "release",
                "download",
                "v6.7.0",
                "--repo",
                "SuperMonster003/AutoJs6",
                "-p",
                APK_NAME,
                "-D",
                str(DL_DIR),
            ],
            check=True,
        )

    if adb.package_installed(serial, AUTOJS_PKG):
        print("AutoJs6 already installed")
    else:
        print("Installing AutoJs6...")
        adb.adb(serial, "install", "-r", str(apk_path), check=True)

    print("Granting Termux RUN_COMMAND to AutoJs6...")
    grant = adb.adb(serial, "shell", "pm", "grant", AUTOJS_PKG, "com.termux.permission.RUN_COMMAND")
    if grant.returncode == 0:
        print("RUN_COMMAND granted")
    else:
        print("WARN: RUN_COMMAND grant failed — use repair-bridge.sh fallback (deployed below)")

    ssh_host = deploy_termux_scripts(alias, serial)

    subprocess.run(
        [sys.executable, str(MAC_DIR / "deploy.py"), alias, *( [device_id] if device_id else [] )],
        check=True,
    )

    adb.adb(serial, "shell", "echo autojs6 > /sdcard/stayturgid/state/automation_mode.txt", check=False)

    harden = REPO_ROOT / "mac" / "harden_fleet_apps.py"
    if harden.is_file():
        print("Hardening fleet app permissions and battery settings...")
        subprocess.run([sys.executable, str(harden), alias], check=False)

    sync = REPO_ROOT / "obtainium" / "mac" / "sync_to_device.py"
    enable = MAC_DIR / "enable_autojs6_shizuku.py"
    if sync.is_file():
        print("Registering AutoJs6 in Obtainium...")
        subprocess.run([sys.executable, str(sync), alias, "autojs6"], check=False)
    if enable.is_file():
        print("Enabling AutoJs6 Shizuku drawer access...")
        subprocess.run([sys.executable, str(enable), alias], check=False)

    print(
        f"""
=== Setup complete ===

On device:
  1. Open AutoJs6 → enable Accessibility service
  2. ./start_watchdog.py {alias}        # or run main.js in AutoJs6
     (Shizuku grant + drawer already ran via enable_autojs6_shizuku.py)

ADB grants: RUN_COMMAND plus fleet harden (storage, notifications, battery unrestricted).

Logs:
  adb -s {serial} shell tail -f /sdcard/stayturgid/logs/watchdog.log
  ssh {ssh_host or alias} 'tail -f ~/.stayturgid/logs/bridge.log'  # if SSH worked
"""
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"ERROR: command failed (exit {exc.returncode})\n")
        sys.exit(exc.returncode or 1)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
