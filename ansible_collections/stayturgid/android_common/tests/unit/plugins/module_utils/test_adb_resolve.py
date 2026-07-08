"""Unit tests for the adb_resolve module_util (control-node ADB target picker)."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_resolve as ar  # noqa: E402


def _listing(*lines):
    """Fake run_command: 'adb devices' returns lines; connect/shell succeed."""
    def run(cmd):
        if cmd[:2] == ["adb", "devices"]:
            return 0, ("\n".join(lines) + "\n") if lines else "", ""
        if cmd[:2] == ["adb", "connect"]:
            return 0, "connected to %s" % cmd[2], ""
        if len(cmd) >= 4 and cmd[:2] == ["adb", "-s"] and cmd[3] == "shell":
            return 0, "RFCX219CHKA\n", ""
        return 1, "", ""
    return run


def _conf(tmp_path, text):
    conf = tmp_path / "devices.conf"
    conf.write_text(text)
    return str(conf)


def test_device_row_parses_and_pads(tmp_path):
    conf = _conf(tmp_path, "# comment\ns24 RFCX 100.1.1.1 192.168.1.9\np7a ONLYUSB\n")
    assert ar.device_row("s24", conf) == ("RFCX", "100.1.1.1", "192.168.1.9")
    assert ar.device_row("p7a", conf) == ("ONLYUSB", "-", "-")
    assert ar.device_row("missing", conf) is None


def test_wireless_endpoints_lan_before_tailscale():
    assert ar.wireless_endpoints(("RFCX", "100.1.1.1", "192.168.1.9")) == [
        "192.168.1.9:5555",
        "100.1.1.1:5555",
    ]
    assert ar.wireless_endpoints(("RFCX", "-", "-")) == []


def test_adb_online_matches_only_device_state():
    listing = "192.168.1.9:5555\tdevice\n100.1.1.1:5555\toffline\n"
    assert ar.adb_online(listing, "192.168.1.9:5555") is True
    assert ar.adb_online(listing, "100.1.1.1:5555") is False


def test_resolve_unknown_alias_passes_through(tmp_path):
    conf = _conf(tmp_path, "s24 RFCX - -\n")
    assert ar.resolve_adb("raw:5555", _listing(), conf) == "raw:5555"


def test_resolve_prefers_online_usb(tmp_path):
    conf = _conf(tmp_path, "s24 RFCX219CHKA 100.1.1.1 192.168.1.9\n")
    assert ar.resolve_adb("s24", _listing("RFCX219CHKA\tdevice"), conf) == "RFCX219CHKA"


def test_resolve_matches_ro_serialno_when_ip_drifts(tmp_path):
    conf = _conf(tmp_path, "s24 RFCX219CHKA 100.1.1.1 192.168.1.55\n")
    # USB serial not directly listed, but a drifted IP reports the same ro.serialno
    assert ar.resolve_adb("s24", _listing("192.168.68.99:5555\tdevice"), conf) == "192.168.68.99:5555"


def test_resolve_static_fallback_without_run_command(tmp_path):
    conf = _conf(tmp_path, "p7a - 100.1.1.1 192.168.1.9\n")
    assert ar.resolve_adb("p7a", None, conf) == "192.168.1.9:5555"


def test_connect_wireless_skips_unreachable(monkeypatch):
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: False)
    calls = []
    ar.connect_wireless(lambda cmd: calls.append(cmd) or (0, "", ""), "192.168.1.9:5555")
    assert calls == []  # never issued the blocking adb connect


def test_connect_wireless_connects_when_reachable(monkeypatch):
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[:2] == ["adb", "devices"]:
            return 0, "192.168.1.9:5555\tdevice\n", ""
        return 0, "", ""

    assert ar.connect_wireless(run, "192.168.1.9:5555") is True
    assert ["adb", "connect", "192.168.1.9:5555"] in calls


def test_resolve_gates_connect_behind_probe(tmp_path, monkeypatch):
    conf = _conf(tmp_path, "p7a USB 100.65.0.1 192.168.1.9\n")
    monkeypatch.setattr(ar, "tcp_reachable",
                        lambda ep, timeout=None: ep == "100.65.0.1:5555")
    seen = []

    def run(cmd):
        seen.append(cmd)
        if cmd[:2] == ["adb", "devices"]:
            if any(c[:2] == ["adb", "connect"] for c in seen):
                return 0, "100.65.0.1:5555\tdevice\n", ""
            return 0, "", ""
        return 0, "", ""

    assert ar.resolve_adb("p7a", run, conf) == "100.65.0.1:5555"
    assert ["adb", "connect", "192.168.1.9:5555"] not in seen
    assert ["adb", "connect", "100.65.0.1:5555"] in seen
