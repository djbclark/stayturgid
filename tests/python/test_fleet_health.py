"""Unit tests for shared/mac/fleet_health.py (no device required)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "mac"))

import fleet_health as fh  # noqa: E402


def test_parse_kv():
    text = "sshd=ok\nwatchdog_age=120\na11y=ok\njunk\n"
    assert fh.parse_kv(text)["sshd"] == "ok"
    assert fh.parse_kv(text)["watchdog_age"] == "120"


def test_evaluate_healthy():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "a11y": "ok",
        "autojs6_a11y": "ok",
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
