"""Unit tests for control/bin/access_monitor.py — the debounce/parse logic."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mac"))
import access_monitor as am  # noqa: E402


def test_read_devices(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# gen\noneui-device RFCX 100.1 192.1\nstock-android-device 3526 100.2 -\nbad\n")
    rows = list(am.read_devices(str(conf)))
    assert rows == [("oneui-device", "100.1", "192.1"), ("stock-android-device", "100.2", "-")]


def test_state_roundtrip(tmp_path):
    sf = str(tmp_path / "oneui-device")
    assert am.read_state(sf) == 0  # missing => 0
    am.write_state(sf, 3)
    assert am.read_state(sf) == 3
    (tmp_path / "junk").write_text("notanumber")
    assert am.read_state(str(tmp_path / "junk")) == 0


def test_recovery_notifies_once_and_resets(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(am, "adb_reachable", lambda addrs: "adb:100.1:5555")
    logs, notifs = [], []
    monkeypatch.setattr(am, "_access_log", lambda _level, message: logs.append(message))
    monkeypatch.setattr(am, "notify", lambda *a, **k: notifs.append(a))

    sf = os.path.join(str(tmp_path), "oneui-device")
    am.write_state(sf, 3)  # was in outage past the limit
    am.check_device("oneui-device", "100.1", "192.1")
    assert am.read_state(sf) == 0
    assert len(notifs) == 1 and "reachable again" in notifs[0][1]


def test_outage_alerts_only_at_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(am, "adb_reachable", lambda addrs: None)
    monkeypatch.setattr(am, "tcp_open", lambda h, p, timeout=5: False)
    notifs = []
    monkeypatch.setattr(am, "_access_log", lambda *_: None)
    monkeypatch.setattr(am, "notify", lambda *a, **k: notifs.append(a))

    # run 1: fails=1, no alert; run 2: fails=2 == limit, one alert; run 3: no repeat
    am.check_device("oneui-device", "100.1", "192.1")
    assert not notifs
    am.check_device("oneui-device", "100.1", "192.1")
    assert len(notifs) == 1 and "LOST" in notifs[0][0]
    am.check_device("oneui-device", "100.1", "192.1")
    assert len(notifs) == 1, "no repeat alert per run during a sustained outage"


def test_ssh_fallback_when_adb_down(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(am, "adb_reachable", lambda addrs: None)
    seen = {}
    monkeypatch.setattr(am, "tcp_open", lambda h, p, timeout=5: seen.setdefault("hp", (h, p)) or True)
    monkeypatch.setattr(am, "_access_log", lambda *_: None)
    monkeypatch.setattr(am, "notify", lambda *a, **k: None)
    am.check_device("oneui-device", "100.1", "192.1")
    assert seen["hp"] == ("100.1", am.SSH_PORT)  # probes the Tailscale ip:8022
    assert am.read_state(os.path.join(str(tmp_path), "oneui-device")) == 0
