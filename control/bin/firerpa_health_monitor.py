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
import sys
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
    print("lamda-client not installed -- skipping FIRERPA health check", file=sys.stderr)
    sys.exit(0)

import json
import subprocess

from control.lib.ansible_context import resolve_ansible_context, resolved_env


def get_fleet() -> dict[str, str]:
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
        return {}

    inv = json.loads(result.stdout)
    hosts = inv.get("stayturgid", {}).get("hosts", [])
    if not hosts:
        # Fallback to children of stayturgid if it's a group of groups
        for child_group in inv.get("stayturgid", {}).get("children", []):
            hosts.extend(inv.get(child_group, {}).get("hosts", []))

    hostvars = inv.get("_meta", {}).get("hostvars", {})

    fleet = {}
    for host in hosts:
        ip = hostvars.get(host, {}).get("ansible_host")
        if ip:
            fleet[host] = ip

    return fleet


def check_device(alias: str, ip: str) -> dict:
    try:
        d = Device(ip, port=65000, certificate=certificate_path())
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


def main() -> int:
    rc = 0
    trim_log(os.path.join(ROOT, "logs", LOG_NAME), max_age_days=30, max_lines=2000)
    fleet = get_fleet()
    if not fleet:
        print("No active devices found in inventory.", file=sys.stderr)
        return 1

    for alias, ip in fleet.items():
        result = check_device(alias, ip)
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

        status = f"firerpa={firerpa} sshd={sshd} shizuku={shizuku}"
        if issues:
            status += f" issues={','.join(issues)}"

        log(LOG_NAME, level, "%s via firerpa:%s:65000: %s" % (alias, ip, status), also_print=False)

    return rc


if __name__ == "__main__":
    sys.exit(main())
