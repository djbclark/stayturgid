"""Unit tests for control/bin/adb_reconnect.py — candidate ordering, parsing, caching."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mac"))
import adb_reconnect as ar  # noqa: E402


def test_build_candidates_order_and_dedup():
    c = ar.build_candidates(
        cached="10.0.0.5:5555", current_ip="192.168.1.9", mdns_addr="192.168.1.9:37000", tailscale_ip="100.1:5555"
    )
    # current LAN first, then cached, then mDNS, then tailscale; no dupes
    assert c == ["192.168.1.9:5555", "10.0.0.5:5555", "192.168.1.9:37000", "100.1:5555"]


def test_build_candidates_dedups_identical():
    c = ar.build_candidates("100.1:5555", None, None, "100.1:5555")
    assert c == ["100.1:5555"]


def test_resolve_target_from_conf(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")
    monkeypatch.setattr(ar, "CONF", str(conf))
    assert ar.resolve_target(["s24"]) == ("RFCX", "192.168.68.55:5555", "100.123:5555")


def test_resolve_target_conf_no_lan(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a 3526 100.65 -\n")
    monkeypatch.setattr(ar, "CONF", str(conf))
    assert ar.resolve_target(["p7a"]) == ("3526", None, "100.65:5555")


def test_resolve_target_legacy_positional(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "CONF", str(tmp_path / "none"))
    assert ar.resolve_target(["SER", "192.1:5555", "100.1:5555"]) == ("SER", "192.1:5555", "100.1:5555")


def test_discover_mdns_matches_serial(monkeypatch):
    out = (
        "_adb-tls-connect._tcp.\n"
        "adb-RFCX219CHKA-abc _adb-tls-connect._tcp. 192.168.68.55:41234\n"
        "adb-OTHER-xyz _adb-tls-connect._tcp. 10.0.0.9:5555\n"
    )
    monkeypatch.setattr(ar, "adb", lambda a, timeout=15: type("R", (), {"stdout": out})())
    assert ar.discover_mdns("RFCX219CHKA") == "192.168.68.55:41234"


def test_discover_lan_ip(monkeypatch):
    out = "    inet 192.168.68.55/24 brd 192.168.68.255 scope global wlan0\n"
    monkeypatch.setattr(ar, "adb", lambda a, timeout=15: type("R", (), {"stdout": out})())
    assert ar.discover_lan_ip("RFCX") == "192.168.68.55"


def test_main_exits_when_already_connected(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")
    monkeypatch.setattr(ar, "CONF", str(conf))
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(ar, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(ar, "is_connected", lambda addr: True)  # already up
    called = {"connect": False}
    monkeypatch.setattr(ar, "adb", lambda a, timeout=15: called.__setitem__("connect", True))
    # cached read will fail (no file) -> default_ip; is_connected True -> return 0
    assert ar.main(["s24"]) == 0
    assert called["connect"] is False, "must not attempt connect when already up"


def test_main_caches_successful_non_mdns(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")
    monkeypatch.setattr(ar, "CONF", str(conf))
    monkeypatch.setattr(ar, "ROOT", str(tmp_path / ".config" / "stayturgid"))
    monkeypatch.setattr(os.path, "exists", lambda p: p == ar.ADB)
    monkeypatch.setattr(ar, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(ar, "is_connected", lambda addr: False)
    # DHCP moved the device to a new LAN IP (differs from cached default)
    monkeypatch.setattr(ar, "discover_lan_ip", lambda s: "192.168.1.99")
    monkeypatch.setattr(ar, "discover_mdns", lambda s: None)
    monkeypatch.setattr(ar, "notify", lambda m: None)
    monkeypatch.setattr(ar, "log", lambda *a: None)
    monkeypatch.setattr(ar, "adb", lambda a, timeout=15: type("R", (), {"stdout": "connected to 192.168.1.99:5555"})())
    rc = ar.main(["s24"])
    assert rc == 0
    cache = os.path.join(str(tmp_path), ".config", "stayturgid", "state", "device_ip_RFCX")
    assert open(cache).read() == "192.168.1.99:5555", "new address cached after DHCP move"
