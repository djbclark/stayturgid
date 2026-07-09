#!/usr/bin/env python3
"""Dead-man's switch: alert when a device is unreachable on ALL access paths.

Runs every 5 minutes via launchd (installed by ansible/playbooks/mac.yml).
For each device it checks every known address for (a) an ADB connection and
(b) an open SSH port. Only when every path fails for CONSECUTIVE_LIMIT
consecutive runs does it fire a macOS notification — one per outage, not one
per run. Recovery resets the counter and notifies once.

Soft health (watchdog/a11y/sshd echo) is a separate agent:
mac/fleet_health_monitor.py → com.stayturgid.fleet-health.

Device list comes from ~/.config/stayturgid/devices.conf (generated from the
Ansible inventory) — no device facts live here.
"""
import datetime
import os
import socket
import subprocess
import sys

ADB = "/opt/homebrew/bin/adb"
# Single Mac root: ~/.config/stayturgid/{devices.conf,logs/,state/}. mkdir on
# demand so a user-deleted dir self-heals.
ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
STATE_DIR = os.path.join(ROOT, "state", "access-monitor")
LOG = os.path.join(ROOT, "logs", "access-monitor.log")
CONSECUTIVE_LIMIT = 2  # 2 runs x 5 min = alert after ~10 min of total outage
SSH_PORT = 8022


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure(path):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


def log(msg):
    try:
        with open(_ensure(LOG), "a") as f:
            f.write("%s  %s\n" % (ts(), msg))
    except OSError:
        pass


def trim_log(max_lines=1000):
    try:
        with open(LOG) as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(LOG, "w") as f:
                f.writelines(lines[-max_lines:])
    except OSError:
        pass


def notify(title, message, sound=None):
    script = 'display notification "%s" with title "%s"' % (message, title)
    if sound:
        script += ' sound name "%s"' % sound
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def read_devices(conf_path):
    """Yield (name, tailscale_ip, lan_ip) from devices.conf."""
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


def adb_reachable(addrs):
    """Return 'adb:<addr>' if any address is connected/connectable, else None."""
    try:
        listed = subprocess.run([ADB, "devices"], capture_output=True, text=True,
                                timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        listed = ""
    for addr in addrs:
        if "%s\tdevice" % addr in listed:
            return "adb:%s" % addr
        try:
            out = subprocess.run([ADB, "connect", addr], capture_output=True,
                                 text=True, timeout=15).stdout
            if "connected to" in out:
                return "adb:%s" % addr
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def tcp_open(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def read_state(state_file):
    try:
        with open(state_file) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def write_state(state_file, n):
    try:
        with open(state_file, "w") as f:
            f.write(str(n))
    except OSError:
        pass


def check_device(name, ts_ip, lan_ip):
    addrs = []
    if lan_ip != "-":
        addrs.append("%s:5555" % lan_ip)
    addrs.append("%s:5555" % ts_ip)

    state_file = os.path.join(STATE_DIR, name)
    fails = read_state(state_file)

    ok = adb_reachable(addrs)
    if not ok and tcp_open(ts_ip, SSH_PORT):
        ok = "ssh:%s" % ts_ip

    if ok:
        if fails >= CONSECUTIVE_LIMIT:
            log("%s RECOVERED via %s" % (name, ok))
            notify("stayturgid access", "%s reachable again (%s)" % (name, ok))
        write_state(state_file, 0)
    else:
        fails += 1
        write_state(state_file, fails)
        log("%s unreachable on all paths (consecutive: %d)" % (name, fails))
        if fails == CONSECUTIVE_LIMIT:
            notify("stayturgid access LOST",
                   "%s unreachable on ALL paths (ADB + SSH) for ~10 min" % name,
                   sound="Basso")


def main():
    if not os.path.exists(ADB):
        return 1
    if not os.path.exists(CONF):
        return 0  # nothing to monitor until mac.yml generates the conf
    os.makedirs(STATE_DIR, exist_ok=True)
    trim_log()
    for name, ts_ip, lan_ip in read_devices(CONF):
        check_device(name, ts_ip, lan_ip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
