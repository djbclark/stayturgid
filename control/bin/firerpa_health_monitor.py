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
import time
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG = os.path.expanduser("~/.config/stayturgid/logs/firerpa-health.log")

try:
    from lamda.client import Device
except ImportError:
    print("lamda-client not installed — skipping FIRERPA health check", file=sys.stderr)
    sys.exit(0)

FLEET = {
    "s24": "100.123.218.30",
    "p7a": "100.65.230.108",
    "hd8": "100.124.55.39",   # USB ADB only — not always-on
}


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)


def check_device(alias: str, ip: str) -> dict:
    try:
        d = Device(ip, port=65000)
        _ = d.server_info()  # verify connectivity
    except Exception as e:
        return {"firerpa": "unreachable", "error": str(e)[:120]}

    result = {"firerpa": d.server_info().version}

    try:
        out = d.execute_script("ss -tlnp 2>/dev/null | grep ':8022 '", timeout=5)
        stdout = getattr(out, 'stdout', b'')
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors='replace')
        result["sshd"] = "up" if ":8022" in (stdout or "") else "down"
    except Exception:
        result["sshd"] = "unknown"

    try:
        out = d.execute_script("ss -tlnp 2>/dev/null | grep ':5555 '", timeout=5)
        stdout = getattr(out, 'stdout', b'')
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors='replace')
        port_5555 = ":5555" in (stdout or "")
        # Port 5555 alone is not sufficient — it can be provided by developer-
        # options wireless debugging, not Shizuku. Confirm with pgrep.
        out2 = d.execute_script("pgrep -f shizuku_server 2>/dev/null", timeout=5)
        stdout2 = getattr(out2, 'stdout', b'')
        if isinstance(stdout2, bytes):
            stdout2 = stdout2.decode(errors='replace')
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
    for alias, ip in FLEET.items():
        result = check_device(alias, ip)
        firerpa = result.get("firerpa", "unreachable")
        sshd = result.get("sshd", "unknown")
        shizuku = result.get("shizuku", "unknown")

        issues = []
        if firerpa == "unreachable":
            issues.append("firerpa_down")
            rc = 1
        if sshd == "down":
            issues.append("sshd_down")
        if shizuku == "down":
            issues.append("shizuku_down")

        status = f"firerpa={firerpa} sshd={sshd} shizuku={shizuku}"
        if issues:
            status += f" issues={','.join(issues)}"

        log(f"{alias} via firerpa:{ip}:65000: {status}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
