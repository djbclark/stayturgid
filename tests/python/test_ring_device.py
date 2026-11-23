"""Unit tests for control/bin/ring_device.py."""

import os
import sys

import pytest

_BIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "control", "bin"))
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import ring_device  # noqa: E402


@pytest.fixture
def devices_conf(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text(
        "# comment\n"
        "s24 SER1 100.0.0.1 192.168.1.1 Galaxy_S24 -\n"
        "t2e SER2 100.0.0.2 192.168.1.2 Titan_2 -\n"
        "hd8 SER3 100.0.0.3 - Fire_HD8 -\n"
    )
    return str(conf)


def test_parse_args_single_default_secs(devices_conf):
    hosts, secs, is_all = ring_device.parse_args(["t2e"], conf_path=devices_conf)
    assert hosts == ["t2e"]
    assert secs == 30
    assert is_all is False


def test_parse_args_all_expands_devices(devices_conf):
    hosts, secs, is_all = ring_device.parse_args(["all", "45"], conf_path=devices_conf)
    assert hosts == ["s24", "t2e", "hd8"]
    assert secs == 45
    assert is_all is True


def test_parse_args_list_comma_and_space(devices_conf):
    hosts, secs, is_all = ring_device.parse_args(["s24,t2e", "hd8", "15"], conf_path=devices_conf)
    assert hosts == ["s24", "t2e", "hd8"]
    assert secs == 15
    assert is_all is False


def test_main_all_succeeds_if_at_least_one_rings(devices_conf, monkeypatch):
    called = []

    def fake_ring(host, secs):
        called.append((host, secs))
        return (host, 0, "") if host == "s24" else (host, 255, "offline")

    monkeypatch.setattr(ring_device, "ring_host", fake_ring)
    rc = ring_device.main(["all"], conf_path=devices_conf)
    assert rc == 0
    assert sorted(called) == [("hd8", 30), ("s24", 30), ("t2e", 30)]


def test_main_explicit_list_fails_if_any_fails(devices_conf, monkeypatch):
    monkeypatch.setattr(
        ring_device,
        "ring_host",
        lambda host, secs: (host, 0, "") if host == "s24" else (host, 255, "offline"),
    )
    rc = ring_device.main(["s24,t2e"], conf_path=devices_conf)
    assert rc == 1
