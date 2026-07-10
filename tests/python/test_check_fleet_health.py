"""Unit tests for mac/check_fleet_health.py (no device required)."""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mac"))

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
    monkeypatch.setattr(cfh, "GUI_AUDIT_LOG", tmp_path / "missing-gui.log")
    rc = cfh.main(["--hours", "24"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "PROBLEMS" in out
    assert "watchdog_stale" in out


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
    monkeypatch.setattr(cfh, "GUI_AUDIT_LOG", tmp_path / "missing-gui.log")
    rc = cfh.main(["--hours", "24"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_latest_gui_audit(tmp_path):
    log = tmp_path / "gui-audit.log"
    log.write_text(
        "2026-07-09 03:14:01  s24 start serial=1.2.3.4:5555 quiet=1\n"
        "2026-07-09 03:14:40  s24 done issues=aurora_filter_fdroid_off shots=/tmp/s24\n"
        "2026-07-09 03:15:00  p7a done issues=none shots=/tmp/p7a\n"
        "2026-07-09 03:15:30  hd8 unreachable — skip (adb_unreachable)\n"
    )
    since = dt.datetime(2026, 7, 9, 0, 0, 0)
    latest = cfh.latest_gui_audit(log, since)
    assert latest["s24"][1] == ["aurora_filter_fdroid_off"]
    assert latest["p7a"][1] == []
    assert "hd8" not in latest


def test_main_reports_gui_audit_gaps(tmp_path, monkeypatch, capsys):
    log = tmp_path / "logs" / "fleet-health.log"
    log.parent.mkdir(parents=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text("%s  s24 via adb:1.2.3.4:5555: sshd=ok issues=none\n" % now)
    state = tmp_path / "state" / "fleet-health"
    state.mkdir(parents=True)
    (state / "s24").write_text("0")
    gui = tmp_path / "logs" / "gui-audit.log"
    gui.write_text(
        "%s  s24 done issues=aurora_autoupdate_on,aurora_filter_fdroid_off shots=/x\n"
        % now
    )
    monkeypatch.setattr(cfh, "LOG", log)
    monkeypatch.setattr(cfh, "STATE_DIR", state)
    monkeypatch.setattr(cfh, "ACCESS_LOG", tmp_path / "missing-access.log")
    monkeypatch.setattr(cfh, "GUI_AUDIT_LOG", gui)
    rc = cfh.main(["--hours", "24"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "gui-audit" in out
    assert "aurora_autoupdate_on" in out
