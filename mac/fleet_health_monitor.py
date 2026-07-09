#!/usr/bin/env python3
"""Dedicated Mac fleet soft-health monitor (launchd every 5 min).

Read-only scrapes of watchdog/repair/a11y/sshd/bootloop/shell5555 when a
device is reachable. Logs to ~/.config/stayturgid/logs/fleet-health.log and
notifies after CONSECUTIVE_LIMIT consecutive soft failures (~10 min).

Reachability-only outages stay in access_monitor.py (separate agent).
Disable with STAYTURGID_SKIP_HEALTH=1.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHARED_MAC = os.path.join(_REPO, "shared", "mac")
if _SHARED_MAC not in sys.path:
    sys.path.insert(0, _SHARED_MAC)
import fleet_health as fh  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
STATE_DIR = os.path.join(ROOT, "state", "fleet-health")
LOG = os.path.join(ROOT, "logs", "fleet-health.log")
CONSECUTIVE_LIMIT = 2
SKIP_HEALTH = os.environ.get("STAYTURGID_SKIP_HEALTH") == "1"
MAX_LOG_LINES = 2000


def ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure(path: str) -> str:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


def log(msg: str) -> None:
    try:
        with open(_ensure(LOG), "a") as f:
            f.write("%s  %s\n" % (ts(), msg))
    except OSError:
        pass


def trim_log(max_lines: int = MAX_LOG_LINES) -> None:
    try:
        with open(LOG) as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(LOG, "w") as f:
                f.writelines(lines[-max_lines:])
    except OSError:
        pass


def notify(title: str, message: str, sound: str | None = None) -> None:
    # Escape quotes for AppleScript.
    message = message.replace("\\", "\\\\").replace('"', '\\"')
    title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = 'display notification "%s" with title "%s"' % (message, title)
    if sound:
        script += ' sound name "%s"' % sound
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def read_devices(conf_path: str):
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    name, _usb, ts_ip = parts[0], parts[1], parts[2]
                    lan = parts[3] if len(parts) > 3 else "-"
                    yield name, ts_ip, lan
    except OSError:
        return


def read_state(state_file: str) -> int:
    try:
        with open(state_file) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def write_state(state_file: str, n: int) -> None:
    try:
        with open(state_file, "w") as f:
            f.write(str(n))
    except OSError:
        pass


def check_device(name: str, ts_ip: str, lan_ip: str) -> None:
    state_file = os.path.join(STATE_DIR, name)
    path, report = fh.probe_device(name, ts_ip, lan_ip)
    if not path:
        log("%s unreachable — skip soft health (see access-monitor)" % name)
        return

    issues = fh.evaluate_health(report, alias=name)
    summary = fh.summarize(report, issues)
    log("%s via %s: %s" % (name, path, summary))

    fails = read_state(state_file)
    if not issues:
        if fails >= CONSECUTIVE_LIMIT:
            log("%s health RECOVERED" % name)
            notify("stayturgid health", "%s soft checks OK again" % name)
        write_state(state_file, 0)
        return

    fails += 1
    write_state(state_file, fails)
    if fails == CONSECUTIVE_LIMIT:
        detail = ",".join(issues)
        if len(detail) > 180:
            detail = detail[:177] + "..."
        notify("stayturgid health", "%s: %s" % (name, detail), sound="Basso")


def main() -> int:
    if SKIP_HEALTH:
        return 0
    if not os.path.exists(CONF):
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    trim_log()
    for name, ts_ip, lan_ip in read_devices(CONF):
        try:
            check_device(name, ts_ip, lan_ip)
        except Exception as e:  # noqa: BLE001
            log("%s probe error: %s" % (name, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
