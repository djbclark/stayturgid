# -*- coding: utf-8 -*-
"""Fleet ADB target resolution (control node).

Pure helpers shared by stayturgid.fdroid, stayturgid.play, and the adb_device
lookup plugin. Mirrors shared/mac/stayturgid_device.py resolve_adb().
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import re

DEFAULT_DEVICES_CONF = os.path.expanduser("~/.config/stayturgid/devices.conf")


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


def connect_wireless(run_command, endpoint):
    if ":" not in endpoint:
        return False
    run_command(["adb", "connect", endpoint])
    return adb_online(adb_devices_output(run_command), endpoint)


def match_usb_serial(run_command, usb_serial, devices):
    """Return connected adb target matching USB serial (direct or ro.serialno)."""
    if not usb_serial or usb_serial == "-":
        return None
    for line in normalize_adb_output(devices).splitlines():
        if "\tdevice" not in line:
            continue
        candidate = line.split()[0]
        if candidate == usb_serial:
            return candidate
        rc, out, _err = run_command(["adb", "-s", candidate, "shell", "getprop", "ro.serialno"])
        if rc == 0 and normalize_adb_output(out) == usb_serial:
            return candidate
    return None


def static_fallback(row, alias):
    """Best-guess target when nothing is reachable (LAN before Tailscale)."""
    endpoints = wireless_endpoints(row)
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
