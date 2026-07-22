"""Unit tests for control/lib/fleet_health.py and control/bin/fleet_health_monitor.py."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
sys.path.insert(0, str(REPO / "control" / "bin"))

import fleet_health as fh
import fleet_health_monitor as fhm


def test_parse_kv():
    text = "sshd=ok\nwatchdog_age=120\na11y=ok\njunk\n"
    assert fh.parse_kv(text)["sshd"] == "ok"
    assert fh.parse_kv(text)["watchdog_age"] == "120"


def test_health_gather_tracks_python_boot_supervisor():
    assert "start_adb\\.py" in fh.HEALTH_GATHER
    assert "start-adb\\.sh" not in fh.HEALTH_GATHER


def test_health_gather_reads_native_agent_log():
    """Dual-run: STATUS and agent_age come from agent.log as well as watchdog."""
    assert "agent.log" in fh.HEALTH_GATHER
    assert "agent_age=" in fh.HEALTH_GATHER
    assert r"\[agent\] STATUS" in fh.HEALTH_GATHER


def test_device_log_epoch():
    parsed = fhm._device_log_epoch("2026-07-13 12:38:56 [watchdog] example failure")
    expected = datetime.datetime(2026, 7, 13, 12, 38, 56).timestamp()
    assert parsed == expected
    assert fhm._device_log_epoch("no timestamp") is None


def test_evaluate_healthy():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "a11y": "ok",
        "autojs6_a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(report) == []


def test_evaluate_watchdog_stale():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": str(fh.WATCHDOG_FRESH_SEC + 1),
        "repair_age": "100",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "watchdog_stale" in issues
    # Settings lists AutoJs6 but watchdog quiet → sticky-a11y heuristic
    assert "autojs6_a11y_stale" in issues


def test_evaluate_autojs6_a11y_stale_missing_watchdog():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": "missing",
        "repair_age": "100",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "watchdog_missing" in issues
    assert "autojs6_a11y_stale" in issues


def test_evaluate_no_a11y_stale_when_autojs_missing():
    """Missing from settings is autojs6_a11y_missing only, not sticky."""
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": str(fh.WATCHDOG_FRESH_SEC + 1),
        "repair_age": "100",
        "a11y": "down",
        "autojs6_a11y": "missing",
    }
    issues = fh.evaluate_health(report)
    assert "autojs6_a11y_missing" in issues
    assert "autojs6_a11y_stale" not in issues


def test_evaluate_shell_bootloop_port():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "down",
        "shell5555": "down",
        "watchdog_age": "10",
        "repair_age": "10",
        "port": "CLOSED_NO_SHELL",
        "shizuku": "down",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "bootloop_down" in issues
    assert "shell5555_down" in issues
    assert "port_closed" in issues
    assert "shizuku_down" in issues


def test_evaluate_a11y_and_ssh_echo():
    report = {
        "ssh_echo": "fail",
        "sshd": "ok",
        "watchdog_age": "10",
        "repair_age": "10",
        "a11y": "FAILED",
        "autojs6_a11y": "missing",
    }
    issues = fh.evaluate_health(report)
    assert "ssh_echo" in issues
    assert "a11y_failed" in issues
    assert "autojs6_a11y_missing" in issues


def test_summarize_includes_issues():
    s = fh.summarize({"sshd": "ok", "watchdog_age": "9"}, ["watchdog_stale"])
    assert "issues=watchdog_stale" in s
    assert "sshd=ok" in s


def test_summarize_includes_agent_age():
    s = fh.summarize({"sshd": "ok", "agent_age": "42", "watchdog_age": "9"}, [])
    assert "agent_age=42" in s


def test_evaluate_agent_missing_is_not_hard_fail():
    """During dual-run, hosts without the APK must not fail fleet health."""
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "agent_age": "missing",
        "a11y": "ok",
        "autojs6_a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(report) == []


def test_monitor_notifies_after_debounce(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "HEAL_STATE_DIR", str(tmp_path / "heal"))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", True)  # isolate notify test
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "99999",
                "repair_age": "10",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )

    class MockResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(fhm.subprocess, "run", lambda *a, **kw: MockResult())
    notifs, logs = [], []
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: notifs.append(a))
    monkeypatch.setattr(fhm, "_fleet_log", lambda _level, message: logs.append(message))

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not notifs
    assert any("watchdog_stale" in m for m in logs)
    fhm.check_device("oneui-device", "100.1", "192.1")
    assert len(notifs) == 1 and "watchdog_stale" in notifs[0][1]


def test_monitor_heals_stale_watchdog(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "HEAL_STATE_DIR", str(tmp_path / "heal"))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm, "WATCHDOG_HEAL_AFTER", 2)
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "99999",
                "repair_age": "10",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )
    calls = []

    def fake_run(args, **kw):
        calls.append(args)

        class R:
            returncode = 0
            stdout = "Starting main.js\n"
            stderr = ""

        return R()

    monkeypatch.setattr(fhm.subprocess, "run", fake_run)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    # Ensure script path exists check passes
    script = tmp_path / "start_watchdog.py"
    script.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setattr(fhm, "REPO", str(tmp_path))
    # maybe_heal looks for control/tools/autojs6/start_watchdog.py under REPO
    (tmp_path / "control" / "tools" / "autojs6").mkdir(parents=True)
    (tmp_path / "control" / "tools" / "autojs6" / "start_watchdog.py").write_text("x")

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not any(any("start_watchdog.py" in str(part) for part in call) for call in calls)
    fhm.check_device("oneui-device", "100.1", "192.1")
    watchdog_calls = [call for call in calls if any("start_watchdog.py" in str(part) for part in call)]
    assert len(watchdog_calls) == 1
    assert watchdog_calls[0][2:] == ["oneui-device", "1.1.1.1:5555"]


def test_monitor_heal_failure_skips_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    heal_dir = tmp_path / "heal"
    monkeypatch.setattr(fhm, "HEAL_STATE_DIR", str(heal_dir))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm, "WATCHDOG_HEAL_AFTER", 1)
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:100.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "watchdog_age": "99999",
                "repair_age": "10",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )

    def fail_run(args, **kw):
        class R:
            returncode = 1
            stdout = "fail"
            stderr = ""

        return R()

    monkeypatch.setattr(fhm.subprocess, "run", fail_run)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    monkeypatch.setattr(fhm, "REPO", str(tmp_path))
    (tmp_path / "control" / "tools" / "autojs6").mkdir(parents=True)
    (tmp_path / "control" / "tools" / "autojs6" / "start_watchdog.py").write_text("x")

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not (heal_dir / "oneui-device").exists()


def test_monitor_skips_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm.fh, "probe_device", lambda *a, **k: (None, {"reachable": "no"}))
    logs = []
    monkeypatch.setattr(fhm, "_fleet_log", lambda _level, message: logs.append(message))
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    fhm.check_device("oneui-device", "100.1", "192.1")
    assert any("unreachable" in m for m in logs)
    assert fhm.read_state(os.path.join(str(tmp_path), "oneui-device")) == 0
