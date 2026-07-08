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


def adb_devices_output(run_command):
    """Return adb devices text; run_command is module.run_command or similar."""
    rc, out, _err = run_command(["adb", "devices"])
    return (out or "") if rc == 0 else ""


def resolve_adb(alias, run_command=None, conf_path=None):
    """USB serial when plugged in, else tailscale host:5555; unknown aliases pass through."""
    row = device_row(alias, conf_path)
    if not row:
        return alias
    usb, ts_ip, _lan = row
    if usb != "-" and run_command is not None:
        devices = adb_devices_output(run_command)
        if re.search(r"^%s\s+device" % re.escape(usb), devices, re.M):
            return usb
    if ts_ip and ts_ip != "-":
        return "%s:5555" % ts_ip
    lan = row[2] if len(row) > 2 else "-"
    if lan and lan != "-":
        return "%s:5555" % lan
    return alias
