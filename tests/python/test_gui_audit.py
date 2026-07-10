"""Unit tests for mac/gui_audit.py helpers (no device required)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mac"))

import gui_audit as ga  # noqa: E402


def test_read_hosts(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text(
        "# comment\n"
        "s24 SER1 1.1.1.1 2.2.2.2\n"
        "\n"
        "p7a SER2 3.3.3.3 -\n"
    )
    assert ga.read_hosts(conf) == ["s24", "p7a"]


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
    conf.write_text("s24 X 1.1.1.1 -\n")
    monkeypatch.setattr(ga, "CONF", conf)
    monkeypatch.setattr(ga, "LOG", tmp_path / "gui-audit.log")
    monkeypatch.setattr(ga, "ART", tmp_path / "art")
    monkeypatch.setattr(ga, "reachable", lambda h: (False, "adb_unreachable"))
    monkeypatch.delenv("STAYTURGID_PRESENCE_QUIET", raising=False)
    monkeypatch.setenv("STAYTURGID_SKIP_PRESENCE", "1")
    rc = ga.main(["s24"])
    assert rc == 0
    assert os.environ.get("STAYTURGID_PRESENCE_QUIET") == "1"
    assert "STAYTURGID_SKIP_PRESENCE" not in os.environ
    log = (tmp_path / "gui-audit.log").read_text()
    assert "unreachable" in log


def test_gui_audit_overrides(tmp_path):
    conf = tmp_path / "overrides.conf"
    conf.write_text(
        "# comment\n"
        "hd8 neo_shizuku_missing  # operator\n"
        "s24 neo_shizuku_missing\n"
    )
    loaded = ga.load_gui_audit_overrides(conf)
    assert loaded["hd8"] == {"neo_shizuku_missing"}
    kept, suppressed = ga.apply_gui_audit_overrides(
        "hd8",
        ["neo_shizuku_missing", "aurora_shizuku_off"],
        loaded,
    )
    assert suppressed == ["neo_shizuku_missing"]
    assert kept == ["aurora_shizuku_off"]
