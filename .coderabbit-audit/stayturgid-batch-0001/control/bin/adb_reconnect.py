#!/usr/bin/env python3
"""Reconnect wireless ADB if the device has dropped.

Runs every 60 seconds via launchd (installed by ansible/playbooks/control_node/agents.yml);
exits silently when already connected. Failure alerting belongs to
access_monitor.py (debounced) — this script never notifies on failure.

Python replacement for adb-reconnect.sh: deterministic parsing of
`adb devices`/`adb mdns services`, regex IP extraction, and cache handling
that behave identically on macOS and Linux.

Usage: adb_reconnect.py <alias>                       (conf-driven, preferred)
       adb_reconnect.py <serial> <ip:port> [ts:port]  (legacy positional)

Candidates, tried in order:
  1. last known-good address (cached per serial)
  2. current LAN IP discovered over USB (handles DHCP changes)
  3. mDNS _adb-tls-connect endpoint (ephemeral port — never cached)
  4. the device's Tailscale address (stable fallback of last resort)
"""

import datetime
import fcntl
import os
import re
import subprocess
import sys

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
try:
    from stayturgid_device import adb_bin as _adb_bin

    ADB = _adb_bin()
except ImportError:
    ADB = os.environ.get("STAYTURGID_ADB", "/opt/homebrew/bin/adb")
# Single Mac root: ~/.config/stayturgid/{devices.conf,logs/,state/}.
ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
LOG = os.path.join(ROOT, "logs", "adb-reconnect.log")
MAX_LINES = 1000
IP_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
IP_PORT_RE = re.compile(r"\d+\.\d+\.\d+\.\d+:\d+")


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _applescript_escape(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _ensure(path):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


def log(serial, msg):
    try:
        with open(_ensure(LOG), "a") as f:
            f.write("%s  [%s] %s\n" % (ts(), serial, msg))
    except OSError:
        pass


def trim_log(max_lines=MAX_LINES):
    lock_path = LOG + ".lock"
    try:
        with open(lock_path, "a") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                with open(LOG) as f:
                    lines = f.readlines()
                if len(lines) > max_lines:
                    with open(LOG, "w") as f:
                        f.writelines(lines[-max_lines:])
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except OSError:
        pass


def adb(args, timeout=15):
    try:
        return subprocess.run([ADB] + args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def device_row(alias, conf_path):
    """alias -> (usb, ts_ip, lan) via shared stayturgid_device parser."""
    try:
        from stayturgid_device import device_row as _device_row

        return _device_row(alias, conf_path)
    except Exception:
        pass
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0] == alias:
                    return tuple((parts[1:] + ["-", "-", "-"])[:3])
    except OSError:
        pass
    return None


def resolve_target(argv):
    """Return (serial, default_ip_or_None, tailscale_ip_or_None) from args/conf."""
    if not argv:
        sys.stderr.write("usage: adb_reconnect.py <alias> | <serial> <ip:port> [ts:port]\n")
        sys.exit(2)
    row = device_row(argv[0], CONF)
    if row:
        usb, ts_ip, lan = row
        serial = argv[0] if usb == "-" else usb
        default_ip = None if lan == "-" else "%s:5555" % lan
        return serial, default_ip, "%s:5555" % ts_ip
    # legacy positional
    if len(argv) < 2:
        sys.stderr.write("legacy mode needs <ip:port>\n")
        sys.exit(2)
    return argv[0], argv[1], (argv[2] if len(argv) > 2 else None)


def is_connected(addr):
    r = adb(["devices"])
    return bool(r and ("%s\tdevice" % addr) in r.stdout)


def discover_lan_ip(serial):
    r = adb(["-s", serial, "shell", "ip addr show wlan0 2>/dev/null | grep 'inet '"])
    if not r:
        return None
    m = IP_RE.search(r.stdout)
    return m.group(0) if m else None


def discover_mdns(serial):
    r = adb(["mdns", "services"])
    if not r:
        return None
    for line in r.stdout.splitlines():
        if ("adb-%s" % serial) in line and "_adb-tls-connect" in line:
            m = IP_PORT_RE.search(line)
            if m:
                return m.group(0)
    return None


def build_candidates(cached, current_ip, mdns_addr, tailscale_ip):
    """Ordered, de-duplicated candidate list."""
    ordered = []
    if current_ip:
        ordered.append("%s:5555" % current_ip)
    if cached:
        ordered.append(cached)
    if mdns_addr:
        ordered.append(mdns_addr)
    if tailscale_ip:
        ordered.append(tailscale_ip)
    seen, out = set(), []
    for a in ordered:
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def notify(msg):
    try:
        subprocess.run(
            ["osascript", "-e", 'display notification "%s" with title "stayturgid"' % _applescript_escape(msg)],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not os.path.exists(ADB):
        return 1
    serial, default_ip, tailscale_ip = resolve_target(argv)

    device_file = os.path.join(ROOT, "state", "device_ip_%s" % serial)
    trim_log()

    try:
        with open(device_file) as f:
            cached = f.read().strip()
    except OSError:
        cached = default_ip or tailscale_ip

    # Already connected on any known-good address?
    for addr in (cached, tailscale_ip):
        if addr and is_connected(addr):
            return 0

    current_ip = discover_lan_ip(serial)
    mdns_addr = discover_mdns(serial)
    candidates = build_candidates(cached, current_ip, mdns_addr, tailscale_ip)

    for addr in candidates:
        log(serial, "trying %s" % addr)
        r = adb(["connect", addr])
        out = r.stdout if r else ""
        log(serial, out.strip() or "(no output)")
        if "connected to" in out:
            # Never cache the mDNS endpoint — its port is ephemeral.
            if addr != cached and addr != mdns_addr:
                os.makedirs(os.path.dirname(device_file), exist_ok=True)
                with open(device_file, "w") as f:
                    f.write(addr)
            notify("Reconnected %s" % addr)
            return 0

    # No notification on failure: access_monitor.py owns outage alerting.
    log(serial, "unreachable on all candidates")
    return 1


if __name__ == "__main__":
    sys.exit(main())
