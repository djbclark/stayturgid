"""Parity tests for Ansible adb_resolve vs control/lib/stayturgid_device."""
import importlib.util
import os
import sys

from pathlib import Path

from conftest import REPO

_MOD = Path(REPO) / "ansible_collections/stayturgid/android_common/plugins/module_utils/adb_resolve.py"
_spec = importlib.util.spec_from_file_location("adb_resolve", _MOD)
adb_resolve = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(adb_resolve)

sys.path.insert(0, str(Path(REPO) / "control" / "lib"))
import stayturgid_device as dev  # noqa: E402


def _devices_listing(*lines):
    def run(cmd):
        if cmd[:2] == ["adb", "devices"]:
            return 0, "\n".join(lines) + "\n", ""
        if cmd[:2] == ["adb", "connect"]:
            return 0, "connected to %s" % cmd[2], ""
        if len(cmd) >= 5 and cmd[:2] == ["adb", "-s"] and cmd[3] == "shell":
            return 0, "RFCX219CHKA\n", ""
        return 1, "", ""
    return run


def test_resolve_adb_lan_fallback(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a - - 192.168.1.9\n")
    assert adb_resolve.resolve_adb("p7a", _devices_listing(), str(conf)) == "192.168.1.9:5555"


def test_resolve_adb_no_dash_tailscale(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX - -\n")

    def no_usb(_cmd):
        return 0, "", ""

    assert adb_resolve.resolve_adb("s24", no_usb, str(conf)) == "s24"


def test_resolve_adb_prefers_online_lan_over_offline_tailscale(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX219CHKA 100.123.218.30 192.168.68.60\n")
    run = _devices_listing("192.168.68.60:5555\tdevice")
    assert adb_resolve.resolve_adb("s24", run, str(conf)) == "192.168.68.60:5555"


def test_resolve_adb_connects_wireless_when_needed(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a 35261JEHN12374 100.65.230.108 192.168.68.65\n")
    # LAN down, Tailscale reachable — probe gates the (blocking) adb connect.
    monkeypatch.setattr(adb_resolve, "tcp_reachable",
                        lambda ep, timeout=None: ep == "100.65.230.108:5555")
    seen = []

    def run(cmd):
        seen.append(cmd)
        if cmd[:2] == ["adb", "devices"]:
            if any(c[:2] == ["adb", "connect"] for c in seen):
                return 0, "100.65.230.108:5555\tdevice\n", ""
            return 0, "", ""
        if cmd[:2] == ["adb", "connect"]:
            return 0, "connected", ""
        return 0, "", ""

    assert adb_resolve.resolve_adb("p7a", run, str(conf)) == "100.65.230.108:5555"
    assert ["adb", "connect", "100.65.230.108:5555"] in seen
    # unreachable LAN endpoint must never reach the blocking adb connect
    assert ["adb", "connect", "192.168.68.65:5555"] not in seen


def test_resolve_adb_skips_connect_for_unreachable_endpoints(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a 35261JEHN12374 100.65.230.108 192.168.68.65\n")
    monkeypatch.setattr(adb_resolve, "tcp_reachable", lambda ep, timeout=None: False)
    seen = []

    def run(cmd):
        seen.append(cmd)
        if cmd[:2] == ["adb", "devices"]:
            return 0, "", ""
        return 1, "", ""

    # nothing reachable -> Tailscale fallback (LAN dead), no adb connect calls
    assert adb_resolve.resolve_adb("p7a", run, str(conf)) == "100.65.230.108:5555"
    assert not any(c[:2] == ["adb", "connect"] for c in seen)


def test_resolve_adb_matches_ro_serialno_when_ip_drifted(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX219CHKA 100.123.218.30 192.168.68.55\n")
    run = _devices_listing("192.168.68.99:5555\tdevice")
    assert adb_resolve.resolve_adb("s24", run, str(conf)) == "192.168.68.99:5555"


def test_stayturgid_device_matches_adb_resolve(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX219CHKA 100.123.218.30 192.168.68.60\n")

    def fake_run(cmd, **kw):
        rc, out, err = _devices_listing("192.168.68.60:5555\tdevice")(cmd)
        return type("R", (), {"returncode": rc, "stdout": out, "stderr": err})()

    monkeypatch.setattr(dev, "_run", fake_run)
    assert dev.resolve_adb("s24", str(conf)) == "192.168.68.60:5555"
