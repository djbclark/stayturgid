"""Unit tests for shared/mac/post_ui_remote.py routing."""
import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "shared",
        "mac",
    ),
)
import post_ui_remote as remote  # noqa: E402


def test_hd8_uses_mac_usb(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: ("usb", "ts", "lan"))
    monkeypatch.setattr(remote.dev, "resolve_ssh_host", lambda a, conf_path=None: "hd8")
    assert remote.host_uses_on_device_ui("hd8") is False


def test_s24_uses_on_device(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: ("usb", "ts", "lan"))
    monkeypatch.setattr(remote.dev, "resolve_ssh_host", lambda a, conf_path=None: "s24")
    assert remote.host_uses_on_device_ui("s24") is True


def test_raw_serial_uses_mac(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: None)
    assert remote.host_uses_on_device_ui("RFCX219CHKA") is False
