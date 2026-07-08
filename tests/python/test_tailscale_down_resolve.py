"""Unit tests for autojs6/mac/test_tailscale_down.py endpoint resolution."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
_MAC = REPO / "autojs6" / "mac" / "test_tailscale_down.py"
_spec = importlib.util.spec_from_file_location("tailscale_down_mac", _MAC)
ttd = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ttd)


def test_resolve_serial_prefers_usb(monkeypatch):
    monkeypatch.setattr(ttd.adb, "adb_devices", lambda: "RFCX219CHKA\tdevice\n")
    monkeypatch.setattr(ttd.dev, "device_row", lambda alias: ("RFCX219CHKA", "100.1.2.3", "192.168.1.10"))
    assert ttd.resolve_serial("s24") == "RFCX219CHKA"


def test_resolve_serial_uses_lan_when_usb_offline(monkeypatch):
    monkeypatch.setattr(
        ttd.adb,
        "adb_devices",
        lambda: "192.168.68.60:5555\tdevice\n100.123.218.30:5555\toffline\n",
    )
    monkeypatch.setattr(
        ttd.dev,
        "device_row",
        lambda alias: ("RFCX219CHKA", "100.123.218.30", "192.168.68.60"),
    )
    assert ttd.resolve_serial("s24") == "192.168.68.60:5555"


def test_resolve_serial_matches_ro_serialno_when_ip_drifted(monkeypatch):
    monkeypatch.setattr(ttd.adb, "adb_devices", lambda: "192.168.68.99:5555\tdevice\n")

    def fake_adb(candidate, *args, **kwargs):
        if args[:2] == ("shell", "getprop"):
            return SimpleNamespace(stdout="RFCX219CHKA\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(ttd.adb, "adb", fake_adb)
    monkeypatch.setattr(
        ttd.dev,
        "device_row",
        lambda alias: ("RFCX219CHKA", "100.123.218.30", "192.168.68.55"),
    )
    assert ttd.resolve_serial("s24") == "192.168.68.99:5555"


def test_resolve_serial_falls_back_to_resolve_target(monkeypatch):
    monkeypatch.setattr(ttd.adb, "adb_devices", lambda: "")
    monkeypatch.setattr(ttd.dev, "device_row", lambda alias: None)
    monkeypatch.setattr(ttd.adb, "resolve_target", lambda alias: "100.1.2.3:5555")
    assert ttd.resolve_serial("s24") == "100.1.2.3:5555"
