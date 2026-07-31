"""Unit tests for control/lib/adb_cli.py."""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
import adb_cli as ac


def test_adb_builds_serial_scoped_argv(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    ac.adb("192.0.2.12:5555", "shell", "true", check=False)
    assert seen["cmd"] == ["adb", "-s", "192.0.2.12:5555", "shell", "true"]
    assert seen["kwargs"]["check"] is False


def test_alias_for_host_forwards_to_stayturgid_device(monkeypatch):
    seen = {}

    def fake_alias_for_host(host):
        seen["host"] = host
        return "hd8"

    monkeypatch.setattr(ac.dev, "alias_for_host", fake_alias_for_host)
    assert ac.alias_for_host("100.124.55.39") == "hd8"
    assert seen["host"] == "100.124.55.39"
