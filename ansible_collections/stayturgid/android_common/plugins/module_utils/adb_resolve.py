# -*- coding: utf-8 -*-
"""Fleet ADB target resolution (control node).

Pure helpers shared by stayturgid.fdroid, stayturgid.play, and the adb_device
lookup plugin. Mirrors control/lib/stayturgid_device.py resolve_adb().
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


try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_FAST_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_dir = os.path.dirname(os.path.abspath(__file__))
    if _mod_dir not in sys.path:
        sys.path.insert(0, _mod_dir)
    from adb_timeout import (
        DEFAULT_FAST_TIMEOUT,
        run_command_with_timeout,
    )


def normalize_adb_output(text):
    return (text or "").replace("\r", "").strip()


def adb_devices_output(run_command, timeout=DEFAULT_FAST_TIMEOUT):
    """Return adb devices text; run_command is module.run_command or similar."""
    rc, out, _err = run_command_with_timeout(run_command, ["adb", "devices"], timeout=timeout)
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


def connect_wireless(run_command, endpoint, *, require_probe=True, timeout=DEFAULT_FAST_TIMEOUT):
    """``adb connect`` to host:port. TCP probe is optional (mDNS wireless-debug
    often fails a plain socket probe but still accepts ``adb connect``).
    """
    if ":" not in endpoint:
        return False
    if require_probe and not tcp_reachable(endpoint):
        return False
    run_command_with_timeout(run_command, ["adb", "connect", endpoint], timeout=timeout)
    return adb_online(adb_devices_output(run_command, timeout=timeout), endpoint)


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


def match_usb_serial(run_command, usb_serial, devices, timeout=DEFAULT_FAST_TIMEOUT):
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
        rc, out, _err = run_command_with_timeout(
            run_command,
            ["adb", "-s", candidate, "shell", "getprop", "ro.serialno"],
            timeout=timeout,
        )
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


def discover_mdns_endpoint(run_command, usb_serial, timeout=DEFAULT_FAST_TIMEOUT):
    """Wireless-debugging mDNS ``host:port`` for a USB serial (Fire / modern ADB).

    ``adb mdns services`` lines look like::

      adb-EXAMPLE-SERIAL-FIRE-Av5cQl_adb-tls-connect._tcp192.0.2.68:39081

    Classic ``ip:5555`` is often refused on Fire while this listener is up.
    """
    if not usb_serial or usb_serial == "-":
        return None
    rc, out, _err = run_command_with_timeout(run_command, ["adb", "mdns", "services"], timeout=timeout)
    if rc != 0:
        return None
    needle = "adb-%s" % usb_serial
    for line in (out or "").splitlines():
        if needle not in line or "_adb-tls-connect" not in line:
            continue
        m = re.search(r"(\d+\.\d+\.\d+\.\d+:\d+)", line)
        if m:
            return m.group(1)
    return None


def resolve_adb(alias, run_command=None, conf_path=None):
    """USB when online, else mDNS wireless-debug, else LAN/TS :5555.

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

    # Prefer wireless-debugging mDNS (ephemeral port) before classic :5555 —
    # Fire HD often has adb_wifi_enabled without listening on 5555. Skip the
    # plain TCP probe — mDNS TLS endpoints often fail socket connect but work
    # with ``adb connect``.
    mdns = discover_mdns_endpoint(run_command, usb)
    if mdns and (adb_online(devices, mdns) or connect_wireless(run_command, mdns, require_probe=False)):
        return mdns

    for endpoint in wireless_endpoints(row):
        if adb_online(devices, endpoint) or connect_wireless(run_command, endpoint):
            return endpoint

    devices = adb_devices_output(run_command)
    match = match_usb_serial(run_command, usb, devices)
    if match:
        return match

    return static_fallback(row, alias)
