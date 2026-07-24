#!/usr/bin/env python3
"""FIRERPA fleet health monitor — checks gRPC connectivity and stayturgid state.

Runs as a Mac launchd agent (com.stayturgid.firerpa-health). For each device
with FIRERPA running, checks:
  1. FIRERPA gRPC reachable on :65000
  2. stayturgid sshd alive (via FIRERPA shell)
  3. Shizuku port 5555 alive (via FIRERPA shell)
  4. Logs status to ~/.config/stayturgid/logs/firerpa-health.log

Usage:
  python3 control/bin/firerpa_health_monitor.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "control" / "lib"):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))
from control.lib.firerpa_auth import certificate_path
from control.lib.site_logging import INFO, WARNING, log, trim_log

LOG_NAME = "firerpa-health.log"
ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")

try:
    from lamda.client import Device
except ImportError:
    Device = None

import json

from control.lib.ansible_context import resolve_ansible_context, resolved_env


@dataclass(frozen=True)
class FirerpaTarget:
    """Inventory-derived FIRERPA policy for one Android host."""

    alias: str
    ip: str
    usb_serial: str = ""
    enabled: bool = True
    runtime_status: str = "supported"
    recovery_mode: str = "none"
    port: int = 65000
    certificate_device_path: str = "/data/local/tmp/firerpa/server/lamda.pem"


LIFECYCLE = (
    REPO_ROOT
    / "ansible_collections"
    / "stayturgid"
    / "firerpa"
    / "roles"
    / "firerpa"
    / "files"
    / "firerpa_lifecycle.py"
)
RECOVERY_MODE_CONTROL_NODE_ADB = "control-node-adb"


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_fleet() -> list[FirerpaTarget]:
    context = resolve_ansible_context(REPO_ROOT)
    env = resolved_env(REPO_ROOT)

    result = subprocess.run(
        ["ansible-inventory", "--list", "-i", str(context.inventory)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("Failed to resolve inventory: " + result.stderr, file=sys.stderr)
        return []

    inv = json.loads(result.stdout)
    hosts = inv.get("stayturgid", {}).get("hosts", [])
    if not hosts:
        # Fallback to children of stayturgid if it's a group of groups
        for child_group in inv.get("stayturgid", {}).get("children", []):
            hosts.extend(inv.get(child_group, {}).get("hosts", []))

    hostvars = inv.get("_meta", {}).get("hostvars", {})

    fleet = []
    for host in hosts:
        variables = hostvars.get(host, {})
        ip = variables.get("ansible_host")
        if ip:
            fleet.append(
                FirerpaTarget(
                    alias=host,
                    ip=str(ip),
                    usb_serial=str(variables.get("device_usb_serial", "")),
                    enabled=_as_bool(variables.get("firerpa_enabled"), True),
                    runtime_status=str(variables.get("firerpa_runtime_status", "supported")),
                    recovery_mode=str(variables.get("firerpa_recovery_mode", "none")),
                    port=int(variables.get("firerpa_port", 65000)),
                    certificate_device_path=str(
                        variables.get(
                            "firerpa_certificate_device_path",
                            "/data/local/tmp/firerpa/server/lamda.pem",
                        )
                    ),
                )
            )

    return fleet


def check_device(alias: str, ip: str, port: int = 65000) -> dict:
    if Device is None:
        return {"firerpa": "unreachable", "error": "lamda-client not installed"}
    try:
        d = Device(ip, port=port, certificate=certificate_path())
        info = d.server_info()
    except Exception as e:
        return {"firerpa": "unreachable", "error": str(e)[:120]}

    result = {"firerpa": info.version}

    try:
        out = d.execute_script("ss -tlnp 2>/dev/null | grep ':8022 '", timeout=5)
        stdout = getattr(out, "stdout", b"")
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        result["sshd"] = "up" if ":8022" in (stdout or "") else "down"
    except Exception:
        result["sshd"] = "unknown"

    try:
        out = d.execute_script("ss -tlnp 2>/dev/null | grep ':5555 '", timeout=5)
        stdout = getattr(out, "stdout", b"")
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        port_5555 = ":5555" in (stdout or "")
        out2 = d.execute_script("pgrep -f '[s]hizuku_server' 2>/dev/null", timeout=5)
        stdout2 = getattr(out2, "stdout", b"")
        if isinstance(stdout2, bytes):
            stdout2 = stdout2.decode(errors="replace")
        shizuku_proc = bool(stdout2 and stdout2.strip())
        if shizuku_proc:
            result["shizuku"] = "up"
        elif port_5555:
            result["shizuku"] = "port_only"
        else:
            result["shizuku"] = "down"
    except Exception:
        result["shizuku"] = "unknown"

    return result


def _adb_reachable(target: str) -> bool:
    try:
        result = subprocess.run(
            ["adb", "-s", target, "shell", "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "ok" in result.stdout


def _recovery_adb_target(target: FirerpaTarget) -> str:
    network_target = f"{target.ip}:5555"
    try:
        subprocess.run(
            ["adb", "connect", network_target],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if _adb_reachable(network_target):
        return network_target
    if target.usb_serial and _adb_reachable(target.usb_serial):
        return target.usb_serial
    return ""


def recover_device(target: FirerpaTarget) -> tuple[bool, str]:
    """Start FIRERPA through the inventory-selected control-node transport."""

    if target.recovery_mode != RECOVERY_MODE_CONTROL_NODE_ADB:
        return False, "not-configured"
    adb_target = _recovery_adb_target(target)
    if not adb_target:
        return False, "adb-unreachable"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(LIFECYCLE),
                "start",
                "--adb-target",
                adb_target,
                f"--port={target.port}",
                f"--certificate={target.certificate_device_path}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "lifecycle-timeout"
    except OSError as exc:
        return False, f"lifecycle-error-{type(exc).__name__}"
    if result.returncode == 0:
        return True, "recovered"
    detail = (result.stderr or result.stdout).strip().splitlines()
    return False, (detail[-1][:120] if detail else f"lifecycle-exit-{result.returncode}")


def main() -> int:
    if Device is None:
        print("lamda-client not installed -- skipping FIRERPA health check", file=sys.stderr)
        return 0
    rc = 0
    trim_log(os.path.join(ROOT, "logs", LOG_NAME), max_age_days=30, max_lines=2000)
    fleet = get_fleet()
    if not fleet:
        print("No active devices found in inventory.", file=sys.stderr)
        return 1

    for target in fleet:
        if target.runtime_status != "supported":
            status = f"firerpa={target.runtime_status} sshd=skip shizuku=skip"
            status += f" issues={target.runtime_status}"
            log(
                LOG_NAME,
                WARNING,
                f"{target.alias} via firerpa:{target.ip}:{target.port}: {status}",
                also_print=False,
            )
            continue
        if not target.enabled:
            log(
                LOG_NAME,
                INFO,
                f"{target.alias} via firerpa:{target.ip}:{target.port}: firerpa=disabled sshd=skip shizuku=skip",
                also_print=False,
            )
            continue

        result = check_device(target.alias, target.ip, target.port)
        recovery = ""
        if result.get("firerpa") == "unreachable" and target.recovery_mode == RECOVERY_MODE_CONTROL_NODE_ADB:
            recovered, recovery = recover_device(target)
            if recovered:
                result = check_device(target.alias, target.ip, target.port)
        firerpa = result.get("firerpa", "unreachable")
        sshd = result.get("sshd", "unknown")
        shizuku = result.get("shizuku", "unknown")

        issues = []
        level = INFO
        if firerpa == "unreachable":
            issues.append("firerpa_down")
            rc = 1
            level = WARNING
        if sshd == "down":
            issues.append("sshd_down")
            level = WARNING
        if shizuku == "down":
            issues.append("shizuku_down")
            level = WARNING
        if recovery and recovery != "recovered":
            issues.append("recovery_failed")
            level = WARNING

        status = f"firerpa={firerpa} sshd={sshd} shizuku={shizuku}"
        if recovery:
            status += f" recovery={recovery}"
        if issues:
            status += f" issues={','.join(issues)}"

        log(
            LOG_NAME,
            level,
            f"{target.alias} via firerpa:{target.ip}:{target.port}: {status}",
            also_print=False,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
