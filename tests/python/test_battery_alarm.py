"""Unit tests for the Python battery-alarm twin (stayturgid_battery_alarm.py).

These test the pure decision logic directly (tiers, wallpaper-backup
validation, quiet detection) — the end-to-end behavior + shell/Python parity
is covered by tests/test-unit.sh (battery_suite run against both twins).
"""
import importlib
import os

import pytest

alarm = importlib.import_module("stayturgid_battery_alarm")


@pytest.mark.parametrize("tier,color,blinks", [
    (30, "purple", 1),
    (25, "blue", 2),
    (20, "green", 3),
    (15, "yellow", 4),
    (10, "orange", 5),
    (5, "red", 10),
    (0, "red", 10),
])
def test_tier_color_and_blinks(tier, color, blinks):
    assert alarm.TIER_COLOR.get(tier, "red") == color
    assert alarm.TIER_BLINKS.get(tier, 10 if tier <= 5 else 1) == blinks


def test_only_lowest_tier_selected():
    # At 12% the applicable tiers are 30/25/20/15; only 15 should fire.
    applicable = [t for t in alarm.TIERS if 12 <= t]
    assert applicable == [30, 25, 20, 15]
    assert applicable[-1] == 15


def test_wallpaper_backup_valid(tmp_path, monkeypatch):
    good = tmp_path / "wp.png"
    good.write_bytes(b"\x89PNG\r\n\x1a\nrest")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(good))
    assert alarm.wallpaper_backup_valid() is True
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(bad))
    assert alarm.wallpaper_backup_valid() is False
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(tmp_path / "missing.png"))
    assert alarm.wallpaper_backup_valid() is False


def test_dnd_detection(monkeypatch):
    calls = {"zen": "0", "filter": "mInterruptionFilter=ALL", "ringer": "2"}
    def fake_adb_shell(*cmd):
        c = " ".join(cmd)
        if "zen_mode" in c:
            return calls["zen"]
        if "dumpsys notification" in c:
            return calls["filter"]
        if "get-ringer-mode" in c:
            return calls["ringer"]
        return ""
    monkeypatch.setattr(alarm, "adb_shell", fake_adb_shell)

    assert alarm.dnd_or_sleep_quiet() is False
    calls["zen"] = "1"
    assert alarm.dnd_or_sleep_quiet() is True
    calls["zen"] = "0"
    calls["filter"] = "mInterruptionFilter=PRIORITY"
    assert alarm.dnd_or_sleep_quiet() is True
    calls["filter"] = "mInterruptionFilter=ALL"
    calls["ringer"] = "0"
    assert alarm.dnd_or_sleep_quiet() is True


def test_malformed_battery_json_exits_zero(monkeypatch):
    monkeypatch.setattr(alarm, "out_of", lambda args: '{"status": "DISCHARGING"}')
    # no percentage => clean exit 0, no crash
    assert alarm.main() == 0
