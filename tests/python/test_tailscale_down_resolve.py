"""Unit tests for control/tools/autojs6/test_tailscale_down.py endpoint resolution."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MAC = REPO / "control" / "tools" / "autojs6" / "test_tailscale_down.py"
_spec = importlib.util.spec_from_file_location("tailscale_down_mac", _MAC)
ttd = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ttd)


def test_resolve_serial_delegates_to_device_helper(monkeypatch):
    monkeypatch.setattr(ttd.dev, "resolve_adb", lambda alias: "192.0.2.12:5555")
    assert ttd.resolve_serial("oneui-device") == "192.0.2.12:5555"


def test_is_tailscale_path_detects_tunnel_target(monkeypatch):
    monkeypatch.setattr(
        ttd.dev,
        "device_row",
        lambda alias: ("EXAMPLE-SERIAL-ONEUI", "100.0.0.12", "192.0.2.65"),
    )
    assert ttd.is_tailscale_path("stock-android-device", "100.0.0.12:5555") is True
    assert ttd.is_tailscale_path("stock-android-device", "192.0.2.65:5555") is False
    assert ttd.is_tailscale_path("stock-android-device", "EXAMPLE-SERIAL-ONEUI") is False


def test_is_tailscale_path_unknown_alias(monkeypatch):
    monkeypatch.setattr(ttd.dev, "device_row", lambda alias: None)
    assert ttd.is_tailscale_path("raw:5555", "raw:5555") is False
