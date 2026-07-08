"""Unit tests for autojs6/mac/test_tailscale_down.py endpoint resolution."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MAC = REPO / "autojs6" / "mac" / "test_tailscale_down.py"
_spec = importlib.util.spec_from_file_location("tailscale_down_mac", _MAC)
ttd = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ttd)


def test_resolve_serial_delegates_to_device_helper(monkeypatch):
    monkeypatch.setattr(ttd.dev, "resolve_adb", lambda alias: "192.168.68.60:5555")
    assert ttd.resolve_serial("s24") == "192.168.68.60:5555"
