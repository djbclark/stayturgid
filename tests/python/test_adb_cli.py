"""Unit tests for control/lib/adb_cli.py and obtainium sync_to_device catalogs."""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
import adb_cli as ac

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "tools", "obtainium"
    ),
)
import sync_to_device as sync


def test_autojs_constants():
    assert ac.AUTOJS_PKG == "org.autojs.autojs6"
    assert ac.AUTOJS_PROJECT_BASE.endswith("/autojs6")


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


def test_start_autojs_file_targets_run_activity(monkeypatch):
    seen = {}
    monkeypatch.setattr(ac, "adb", lambda serial, *args, **kw: seen.update(serial=serial, args=args))
    ac.start_autojs_file("s24serial", "/sdcard/stayturgid/autojs6/scripts/x.js")
    args = seen["args"]
    assert "am" in args and "start" in args
    assert "file:///sdcard/stayturgid/autojs6/scripts/x.js" in args
    assert f"{ac.AUTOJS_PKG}/{ac.AUTOJS_RUN}" in args


def test_sync_catalog_paths_exist():
    for which, (json_path, dest_name) in sync.CATALOGS.items():
        assert json_path.is_file(), which
        assert dest_name.startswith("stayturgid-obtainium-")


def test_alias_for_host_forwards_to_stayturgid_device(monkeypatch):
    seen = {}

    def fake_alias_for_host(host):
        seen["host"] = host
        return "hd8"

    monkeypatch.setattr(ac.dev, "alias_for_host", fake_alias_for_host)
    assert ac.alias_for_host("100.124.55.39") == "hd8"
    assert seen["host"] == "100.124.55.39"
