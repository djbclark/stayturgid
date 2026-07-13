"""Unit tests for control/bin/check_fleet_health.py (no device required)."""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))

import check_fleet_health as cfh  # noqa: E402


def test_latest_per_host(tmp_path):
    log = tmp_path / "fleet-health.log"
    log.write_text(
        "2026-07-09 10:00:00  s24 via adb:1.2.3.4:5555: sshd=ok issues=none\n"
        "2026-07-09 10:05:00  s24 via adb:1.2.3.4:5555: sshd=ok issues=watchdog_stale\n"
        "2026-07-09 10:05:01  p7a via adb:2.2.2.2:5555: sshd=ok issues=none\n"
        "2026-07-09 10:06:00  hd8 unreachable — skip soft health (see access-monitor)\n"
    )
    since = dt.datetime(2026, 7, 9, 9, 0, 0)
    latest = cfh.latest_per_host(log, since)
    assert "watchdog_stale" in latest["s24"][1]
    assert "issues=none" in latest["p7a"][1]
    assert "hd8" not in latest


def test_latest_per_host_accepts_severity_column(tmp_path):
    log = tmp_path / "fleet-health.log"
    log.write_text(
        "2026-07-13 12:55:00  INFO s24 via adb:1.2.3.4:5555: "
        "sshd=ok issues=watchdog_stale\n"
        "2026-07-13 12:55:01  INFO p7a via adb:2.2.2.2:5555: "
        "sshd=ok issues=none\n"
    )

    latest = cfh.latest_per_host(log, dt.datetime(2026, 7, 13, 12, 0, 0))

    assert set(latest) == {"s24", "p7a"}
    assert "watchdog_stale" in latest["s24"][1]


def test_access_host_accepts_severity_column():
    line = (
        "2026-07-13 12:22:51  WARNING hd8 unreachable on all paths "
        "(consecutive: 2)"
    )
    assert cfh.host_from_access_line(line) == "hd8"


def test_issues_from_rest():
    assert cfh.issues_from_rest("sshd=ok issues=none") == []
    assert cfh.issues_from_rest("issues=watchdog_stale,repair_stale") == [
        "watchdog_stale",
        "repair_stale",
    ]


def test_main_reports_problems(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text(
        "%s  s24 via adb:1.2.3.4:5555: sshd=ok watchdog_age=9 issues=watchdog_stale\n" % now
    )
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("3")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", tmp_path / "missing-access.log")
    rc = cfh.main(["--hours", "24"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "PROBLEMS" in out
    assert "watchdog_stale" in out


def test_main_ok_with_stale_access_lost(tmp_path, monkeypatch, capsys):
    """Recovered host: old access LOST must not fail triage or make health."""
    log = tmp_path / "logs" / "fleet-health.log"
    access = tmp_path / "logs" / "access-monitor.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Within the default --hours window (relative, not a hard-coded date).
    old = (dt.datetime.now() - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    log.write_text("%s  s24 via adb:1.2.3.4:5555: sshd=ok issues=none\n" % now)
    access.write_text(
        "%s  s24 unreachable on all paths (consecutive: 2)\n" % old
    )
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("0")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", access)
    rc = cfh.main(["--hours", "24"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "resolved access-monitor" in out


def test_soft_issue_still_resolves_old_access_loss(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    access = tmp_path / "logs" / "access-monitor.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old = (dt.datetime.now() - dt.timedelta(hours=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    log.write_text(
        "%s  INFO s24 via adb:1.2.3.4:5555: sshd=ok "
        "issues=watchdog_stale\n" % now
    )
    access.write_text(
        "%s  WARNING s24 unreachable on all paths (consecutive: 2)\n" % old
    )
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("3")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", access)

    rc = cfh.main(["--hours", "24"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "resolved access-monitor" in out
    assert "recent access-monitor LOST" not in out


def test_main_fails_access_lost_when_host_not_ok(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    access = tmp_path / "logs" / "access-monitor.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text("%s  p7a via adb:1.2.3.4:5555: sshd=ok issues=none\n" % now)
    access.write_text(
        "%s  s24 unreachable on all paths (consecutive: 2)\n"
        % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "p7a").write_text("0")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", access)
    rc = cfh.main(["--hours", "24"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "PROBLEMS" in out
    assert "s24 unreachable" in out


def test_main_ok(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text("%s  s24 via adb:1.2.3.4:5555: sshd=ok issues=none\n" % now)
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("0")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", tmp_path / "missing-access.log")
    rc = cfh.main(["--hours", "24"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_summarize_device_errors_groups_and_classifies():
    now = dt.datetime.now()
    entries = [
        (now - dt.timedelta(minutes=3), "p7a", "watchdog failed"),
        (now - dt.timedelta(minutes=2), "p7a", "watchdog   failed"),
        (now - dt.timedelta(minutes=1), "s24", "bridge unavailable"),
        (now - dt.timedelta(minutes=1), "hd8", "old failure"),
    ]
    summary = cfh.summarize_device_errors(entries, {"s24"}, {"p7a"})
    assert summary["active"][0][0] == "s24: bridge unavailable"
    assert summary["active"][0][1] == 1
    assert summary["recovered"][0][0] == "p7a: watchdog failed"
    assert summary["recovered"][0][1] == 2
    assert summary["historical"][0][0] == "hd8: old failure"


def test_main_groups_recovered_device_errors(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    errors = tmp_path / "logs" / "errors.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    old = (now - dt.timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    log.write_text(
        "%s  s24 via adb:1.2.3.4:5555: sshd=ok issues=none\n"
        "%s  hd8 via adb:2.2.2.2:5555: sshd=ok issues=watchdog_stale\n"
        % (stamp, stamp)
    )
    errors.write_text(
        "%s  ERR s24: %s [watchdog] transient failure\n"
        "%s  ERR s24: %s [watchdog] transient failure\n"
        % (old, old, stamp, stamp)
    )
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("0")
    (state / "hd8").write_text("3")
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "ERROR_LOG", errors)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", tmp_path / "missing-access.log")

    assert cfh.main(["--hours", "24"]) == 1
    out = capsys.readouterr().out
    assert "recovered device errors" in out
    assert "s24: [watchdog] transient failure (x2" in out
    assert out.count("transient failure") == 1
