"""Unit tests for control/bin/gui_audit.py helpers (no device required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))

import gui_audit as ga


def test_read_hosts(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# comment\noneui-device SER1 1.1.1.1 2.2.2.2\n\nstock-android-device SER2 3.3.3.3 -\n")
    assert ga.read_hosts(conf) == ["oneui-device", "stock-android-device"]


def test_main_dry_reach_no_hosts(tmp_path, monkeypatch, capsys):
    conf = tmp_path / "empty.conf"
    conf.write_text("# none\n")
    monkeypatch.setattr(ga, "CONF", conf)
    monkeypatch.setattr(ga, "LOG", tmp_path / "gui-audit.log")
    monkeypatch.setattr(ga, "ART", tmp_path / "art")
    rc = ga.main(["--dry-reach"])
    assert rc == 0
    assert "no_hosts" in (tmp_path / "gui-audit.log").read_text()


def test_quiet_env_set(monkeypatch, tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("oneui-device X 1.1.1.1 -\n")
    monkeypatch.setattr(ga, "CONF", conf)
    monkeypatch.setattr(ga, "LOG", tmp_path / "gui-audit.log")
    monkeypatch.setattr(ga, "ART", tmp_path / "art")
    monkeypatch.setattr(ga, "reachable", lambda h: (False, "adb_unreachable"))
    monkeypatch.delenv("STAYTURGID_PRESENCE_QUIET", raising=False)
    monkeypatch.setenv("STAYTURGID_SKIP_PRESENCE", "1")
    rc = ga.main(["oneui-device"])
    assert rc == 0
    assert os.environ.get("STAYTURGID_PRESENCE_QUIET") == "1"
    assert "STAYTURGID_SKIP_PRESENCE" not in os.environ
    log = (tmp_path / "gui-audit.log").read_text()
    assert "unreachable" in log


def test_gui_audit_overrides(tmp_path):
    conf = tmp_path / "overrides.conf"
    conf.write_text("# comment\nfireos-device neo_shizuku_missing  # operator\noneui-device neo_shizuku_missing\n")
    loaded = ga.load_gui_audit_overrides(conf)
    assert loaded["fireos-device"] == {"neo_shizuku_missing"}
    kept, suppressed = ga.apply_gui_audit_overrides(
        "fireos-device",
        ["neo_shizuku_missing", "aurora_shizuku_off"],
        loaded,
    )
    assert suppressed == ["neo_shizuku_missing"]
    assert kept == ["aurora_shizuku_off"]


def test_vlm_aurora_autoupdate_issues_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(ga.vh, "issue_tags_from_verify", lambda *a, **k: [])
    assert ga.vlm_aurora_autoupdate_issues(tmp_path / "x.png") == []


def test_vlm_aurora_autoupdate_issues_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(ga.vh, "issue_tags_from_verify", lambda shot, check, tag: [tag])
    shot = tmp_path / "14.png"
    shot.write_bytes(b"x")
    assert ga.vlm_aurora_autoupdate_issues(shot) == ["aurora_autoupdate_on_vlm"]
