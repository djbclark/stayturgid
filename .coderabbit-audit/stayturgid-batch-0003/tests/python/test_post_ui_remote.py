"""Unit tests for control/lib/post_ui_remote.py routing."""

import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "control",
        "lib",
    ),
)
import post_ui_remote as remote


def test_hd8_uses_mac_usb(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: ("usb", "ts", "lan"))
    monkeypatch.setattr(remote.dev, "resolve_ssh_host", lambda a, conf_path=None: "fireos-device")
    assert remote.host_uses_on_device_ui("fireos-device") is False


def test_s24_uses_on_device(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: ("usb", "ts", "lan"))
    monkeypatch.setattr(remote.dev, "resolve_ssh_host", lambda a, conf_path=None: "oneui-device")
    assert remote.host_uses_on_device_ui("oneui-device") is True


def test_raw_serial_uses_mac(monkeypatch):
    monkeypatch.setattr(remote.dev, "device_row", lambda a, conf_path=None: None)
    assert remote.host_uses_on_device_ui("EXAMPLE-SERIAL-ONEUI") is False


def test_run_with_mac_fallback_skips_ssh_for_hd8(monkeypatch):
    calls = []

    def boom(*_a, **_k):
        raise AssertionError("ssh_run_on_device must not run for fireos-device")

    monkeypatch.setattr(remote, "ssh_run_on_device", boom)
    monkeypatch.setattr(remote, "host_uses_on_device_ui", lambda _a: False)

    def mac():
        calls.append("mac")
        return 0

    assert remote.run_with_mac_fallback("fireos-device", "script.py", [], mac) == 0
    assert calls == ["mac"]


def test_run_with_mac_fallback_ssh_success(monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "host_uses_on_device_ui", lambda _a: True)
    monkeypatch.setattr(remote, "ssh_run_on_device", lambda *_a, **_k: calls.append("ssh") or 0)

    def mac():
        calls.append("mac")
        return 0

    assert remote.run_with_mac_fallback("oneui-device", "script.py", ["all"], mac) == 0
    assert calls == ["ssh"]


def test_run_with_mac_fallback_ssh_fail_then_mac(monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "host_uses_on_device_ui", lambda _a: True)
    monkeypatch.setattr(remote, "ssh_run_on_device", lambda *_a, **_k: calls.append("ssh") or 1)

    def mac():
        calls.append("mac")
        return 0

    assert remote.run_with_mac_fallback("oneui-device", "script.py", [], mac) == 0
    assert calls == ["ssh", "mac"]


def test_run_with_mac_fallback_both_fail(monkeypatch):
    monkeypatch.setattr(remote, "host_uses_on_device_ui", lambda _a: True)
    monkeypatch.setattr(remote, "ssh_run_on_device", lambda *_a, **_k: 127)

    def mac():
        return 3

    assert remote.run_with_mac_fallback("stock-android-device", "script.py", [], mac) == 3
