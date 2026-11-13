"""Unit tests for control/bin/power_unplug_alert.py: transition logic and the afplay call."""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "bin")
)
import power_unplug_alert as pua

AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t23%; charging; 2:29 remaining present: true\n"
BATT = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t23%; discharging; 3:00 remaining present: true\n"
NEVER = float("-inf")


def test_parse_source():
    assert pua.parse_source(AC) == "ac"
    assert pua.parse_source(BATT) == "battery"
    assert pua.parse_source("Now drawing from 'UPS Power'\n") is None
    assert pua.parse_source("") is None


def test_only_ac_to_battery_rings():
    assert pua.should_ring("ac", "battery", NEVER, 100.0)
    assert not pua.should_ring("battery", "ac", NEVER, 100.0)  # plugging in
    assert not pua.should_ring("ac", "ac", NEVER, 100.0)  # charge-level tick
    assert not pua.should_ring("battery", "battery", NEVER, 100.0)
    assert not pua.should_ring(None, "battery", NEVER, 100.0)  # unknown start
    assert not pua.should_ring("ac", None, NEVER, 100.0)


def test_duplicate_notification_inside_gap_is_ignored():
    assert not pua.should_ring("ac", "battery", 100.0, 100.0 + pua.MIN_GAP_SEC - 0.1)
    assert pua.should_ring("ac", "battery", 100.0, 100.0 + pua.MIN_GAP_SEC)


def test_ring_plays_two_seconds_of_the_battery_sound(monkeypatch):
    calls = []
    monkeypatch.setattr(pua.subprocess, "run", lambda argv, **kw: calls.append(argv))
    assert pua.ring()
    assert calls == [["afplay", "-t", "2", str(pua.SOUND_FILE)]]
    assert pua.SOUND_FILE.name == "locate.mp3"
    assert pua.SOUND_FILE.exists()


def test_ring_skips_missing_sound(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pua.subprocess, "run", lambda argv, **kw: calls.append(argv))
    assert not pua.ring(Path(tmp_path / "nope.mp3"))
    assert calls == []
