"""Tests for fleet_health_monitor.maybe_nag_tasker_recover.

The Tasker SSHD_RECOVER profile is created by hand per phone, so the monitor
self-tests it with a broadcast and nags the operator only when a broadcast
from an earlier pass went unanswered.
"""

from __future__ import annotations

import os
import time

import adb_cli
import fleet_health as fh
import fleet_health_monitor as monitor
import pytest

TARGET = "100.64.0.9:5555"
STALE = {"tasker_recover_age": "missing"}


class _Result:
    returncode = 0
    stdout = "Broadcast completed: result=0"
    stderr = ""


@pytest.fixture
def env(monkeypatch, tmp_path):
    probe_dir = tmp_path / "tasker-recover-probe"
    nag_dir = tmp_path / "tasker-recover-nag"
    monkeypatch.setattr(monitor, "TASKER_RECOVER_PROBE_STATE_DIR", str(probe_dir))
    monkeypatch.setattr(monitor, "TASKER_RECOVER_NAG_STATE_DIR", str(nag_dir))
    monkeypatch.setattr(monitor, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(monitor, "_fleet_log", lambda *a, **k: None)

    calls = {"adb": [], "notify": []}

    def fake_adb(serial, *args, **kwargs):
        calls["adb"].append((serial, args))
        return _Result()

    monkeypatch.setattr(adb_cli, "adb", fake_adb)
    monkeypatch.setattr(monitor, "notify", lambda *a, **k: calls["notify"].append(a))
    calls["probe"] = probe_dir / "hd8"
    calls["nag"] = nag_dir / "hd8"
    return calls


def _age(path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_fresh_does_nothing(env):
    monitor.maybe_nag_tasker_recover("hd8", {"tasker_recover_age": "60"}, TARGET)
    assert env["adb"] == []
    assert env["notify"] == []
    assert not env["probe"].exists()


def test_notasker_does_nothing(env):
    monitor.maybe_nag_tasker_recover("hd8", {"tasker_recover_age": "notasker"}, TARGET)
    assert env["adb"] == []
    assert env["notify"] == []


def test_stale_first_pass_fires_broadcast_without_notify(env):
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    assert env["adb"] == [(TARGET, ("shell", "am", "broadcast", "-a", "com.stayturgid.SSHD_RECOVER"))]
    assert env["notify"] == []
    assert env["probe"].exists()


def test_stale_second_pass_notifies_once(env):
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    _age(env["probe"], 5 * 60)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    # Probe cooldown (1h) holds the second broadcast back.
    assert len(env["adb"]) == 1
    assert len(env["notify"]) == 1
    title, message = env["notify"][0]
    assert title == "stayturgid: action needed"
    assert "hd8" in message and "Keyguard-proof sshd recovery" in message


def test_nag_cooldown_suppresses_third(env):
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    _age(env["probe"], 5 * 60)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    _age(env["probe"], 10 * 60)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    assert len(env["notify"]) == 1


def test_nag_repeats_after_cooldown(env):
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    _age(env["probe"], 5 * 60)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    _age(env["nag"], monitor.TASKER_RECOVER_NAG_COOLDOWN_SEC + 1)
    _age(env["probe"], 2 * 60 * 60)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    assert len(env["adb"]) == 2
    assert len(env["notify"]) == 2


def test_old_probe_from_last_weekly_selftest_does_not_nag(env):
    """A working phone's marker ages past the window right after its last
    probe did; that old probe is not an unanswered one."""
    stale_age = {"tasker_recover_age": str(fh.TASKER_RECOVER_FRESH_SEC + 60)}
    env["probe"].parent.mkdir(parents=True)
    env["probe"].write_text("0")
    _age(env["probe"], fh.TASKER_RECOVER_FRESH_SEC + 70)
    monitor.maybe_nag_tasker_recover("hd8", stale_age, TARGET)
    assert len(env["adb"]) == 1
    assert env["notify"] == []


def test_no_target_no_broadcast_no_crash(env):
    monitor.maybe_nag_tasker_recover("hd8", STALE, None)
    monitor.maybe_nag_tasker_recover("hd8", STALE, None)
    assert env["adb"] == []
    assert env["notify"] == []


def test_failed_broadcast_is_not_stamped(env, monkeypatch):
    class Failed(_Result):
        returncode = 1
        stderr = "error: device offline"

    monkeypatch.setattr(adb_cli, "adb", lambda *a, **k: Failed())
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    assert not env["probe"].exists()
    assert env["notify"] == []


def test_adb_exception_never_raises(env, monkeypatch):
    def boom(*a, **k):
        raise OSError("adb missing")

    monkeypatch.setattr(adb_cli, "adb", boom)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
    assert env["notify"] == []


def test_unexpected_error_never_raises(env, monkeypatch):
    def boom(_report):
        raise RuntimeError("bad report")

    monkeypatch.setattr(fh, "tasker_recover_stale", boom)
    monitor.maybe_nag_tasker_recover("hd8", STALE, TARGET)
