# -*- coding: utf-8 -*-
"""Fleet ADB target resolution (control node).

Pure helpers shared by stayturgid.fdroid, stayturgid.play, and the adb_device
lookup plugin. Mirrors shared/mac/stayturgid_device.py resolve_adb().
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import re
import socket

DEFAULT_DEVICES_CONF = os.path.expanduser("~/.config/stayturgid/devices.conf")

# adb connect to an unreachable host blocks for adb's own (long) timeout; probe
# the TCP port first so a down LAN/Tailscale endpoint fails fast.
CONNECT_PROBE_TIMEOUT = 1.5


def devices_conf_path():
    return os.environ.get("STAYTURGID_DEVICES_CONF", DEFAULT_DEVICES_CONF)


def device_row(alias, conf_path=None):
    """alias -> (usb_serial, tailscale_ip, lan_ip) or None."""
    conf_path = conf_path or devices_conf_path()
    try:
        with open(conf_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0] == alias:
                    return tuple((parts[1:] + ["-", "-", "-"])[:3])
    except OSError:
        pass
    return None


def normalize_adb_output(text):
    return (text or "").replace("\r", "").strip()


def adb_devices_output(run_command):
    """Return adb devices text; run_command is module.run_command or similar."""
    rc, out, _err = run_command(["adb", "devices"])
    return (out or "") if rc == 0 else ""


def adb_online(devices, target):
    return re.search(r"^%s\s+device" % re.escape(target), normalize_adb_output(devices), re.M) is not None


def wireless_endpoints(row):
    """LAN before Tailscale — LAN is usually lower latency when both are up."""
    _usb, ts_ip, lan = row
    endpoints = []
    if lan and lan != "-":
        endpoints.append("%s:5555" % lan)
    if ts_ip and ts_ip != "-":
        endpoints.append("%s:5555" % ts_ip)
    return endpoints


def tcp_reachable(endpoint, timeout=CONNECT_PROBE_TIMEOUT):
    """Fast TCP probe of host:port so adb connect never blocks on a dead endpoint."""
    if ":" not in endpoint:
        return False
    host, _, port = endpoint.rpartition(":")
    try:
        port = int(port)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect_wireless(run_command, endpoint):
    if ":" not in endpoint:
        return False
    if not tcp_reachable(endpoint):
        return False
    run_command(["adb", "connect", endpoint])
    return adb_online(adb_devices_output(run_command), endpoint)


def adb_device_id(line):
    """Serial from an adb devices line (handles mDNS ids with spaces)."""
    if "\t" not in line:
        return None
    state = line.rsplit("\t", 1)[-1].strip()
    if state != "device":
        return None
    return line.rsplit("\t", 1)[0].strip()


def transport_rank(candidate):
    """Lower is better: USB < mDNS wireless-debug < ip:5555 (LAN/Tailscale)."""
    if ":" not in candidate:
        return 0
    if "_adb-tls-connect" in candidate:
        return 1
    return 2


def match_usb_serial(run_command, usb_serial, devices):
    """Return connected adb target matching USB serial (direct or ro.serialno)."""
    if not usb_serial or usb_serial == "-":
        return None
    matches = []
    for line in normalize_adb_output(devices).splitlines():
        candidate = adb_device_id(line)
        if not candidate:
            continue
        if candidate == usb_serial:
            matches.append(candidate)
            continue
        rc, out, _err = run_command(["adb", "-s", candidate, "shell", "getprop", "ro.serialno"])
        if rc == 0 and normalize_adb_output(out) == usb_serial:
            matches.append(candidate)
    if not matches:
        return None
    return sorted(matches, key=transport_rank)[0]


def static_fallback(row, alias):
    """Best-guess target when nothing is in adb devices yet.

    Prefer the first TCP-open wireless endpoint; if none respond, return
    Tailscale over LAN (LAN IPs drift when the phone changes Wi-Fi).
    """
    endpoints = wireless_endpoints(row)
    for ep in endpoints:
        if tcp_reachable(ep):
            return ep
    if len(endpoints) > 1:
        return endpoints[-1]
    if endpoints:
        return endpoints[0]
    return alias


def resolve_adb(alias, run_command=None, conf_path=None):
    """USB when online, else first reachable wireless endpoint (LAN then Tailscale).

    When run_command is provided, tries adb connect for wireless targets and
  scans connected devices by ro.serialno when inventory IPs drift.
    """
    row = device_row(alias, conf_path)
    if not row:
        return alias

    if run_command is None:
        return static_fallback(row, alias)

    devices = adb_devices_output(run_command)
    usb, _ts_ip, _lan = row

    match = match_usb_serial(run_command, usb, devices)
    if match:
        return match

    for endpoint in wireless_endpoints(row):
        if adb_online(devices, endpoint) or connect_wireless(run_command, endpoint):
            return endpoint

    devices = adb_devices_output(run_command)
    match = match_usb_serial(run_command, usb, devices)
    if match:
        return match

    return static_fallback(row, alias)
