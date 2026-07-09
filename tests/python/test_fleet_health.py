"""Unit tests for shared/mac/fleet_health.py and mac/fleet_health_monitor.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "mac"))
sys.path.insert(0, str(REPO / "mac"))

import fleet_health as fh  # noqa: E402
import fleet_health_monitor as fhm  # noqa: E402


def test_parse_kv():
    text = "sshd=ok\nwatchdog_age=120\na11y=ok\njunk\n"
    assert fh.parse_kv(text)["sshd"] == "ok"
    assert fh.parse_kv(text)["watchdog_age"] == "120"


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
    assert "watchdog_stale" in fh.evaluate_health(report)


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


def test_monitor_notifies_after_debounce(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
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
    notifs, logs = [], []
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: notifs.append(a))
    monkeypatch.setattr(fhm, "log", lambda m: logs.append(m))

    fhm.check_device("s24", "100.1", "192.1")
    assert not notifs
    assert any("watchdog_stale" in m for m in logs)
    fhm.check_device("s24", "100.1", "192.1")
    assert len(notifs) == 1 and "watchdog_stale" in notifs[0][1]


def test_monitor_skips_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm.fh, "probe_device", lambda *a, **k: (None, {"reachable": "no"}))
    logs = []
    monkeypatch.setattr(fhm, "log", lambda m: logs.append(m))
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    fhm.check_device("s24", "100.1", "192.1")
    assert any("unreachable" in m for m in logs)
    assert fhm.read_state(os.path.join(str(tmp_path), "s24")) == 0
