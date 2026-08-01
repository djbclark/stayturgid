"""Unit tests for control/lib/stats.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import stats


def _read_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_record_event_default_only_goes_to_events_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    stats.record_event("connection_path", "p7a", via="adb:1.1.1.1:5555")

    events = _read_jsonl(tmp_path / "stats" / "events.jsonl")
    assert len(events) == 1
    assert events[0]["type"] == "connection_path"
    # soft_health.jsonl must not be touched for unrelated event types.
    assert not (tmp_path / "stats" / "soft_health.jsonl").is_file()


def test_record_event_device_log_failure_rides_soft_health_pipe(tmp_path, monkeypatch):
    """device_log_failure must dual-write to soft_health.jsonl so it reaches
    OpenObserve through the existing Vector file source with no new Vector
    config — Vector's file source only tails soft_health.jsonl (see
    control/site_contract/sync_templates/fragments/vector/stayturgid_sources.yaml.j2)."""
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    stats.record_event(
        "device_log_failure",
        "hd8",
        source="watchdog.log",
        severity="ERR",
        message="Tailscale repair FAILED (runtime=down policy=down)",
    )

    events = _read_jsonl(tmp_path / "stats" / "events.jsonl")
    soft_health = _read_jsonl(tmp_path / "stats" / "soft_health.jsonl")
    assert len(events) == 1
    assert len(soft_health) == 1
    assert soft_health[0]["type"] == "device_log_failure"
    assert soft_health[0]["device"] == "hd8"
    assert soft_health[0]["source"] == "watchdog.log"
    assert soft_health[0]["severity"] == "ERR"


def test_record_event_soft_health_still_dual_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    stats.record_event("soft_health", "p7a", port="open")

    soft_health = _read_jsonl(tmp_path / "stats" / "soft_health.jsonl")
    assert len(soft_health) == 1
    assert soft_health[0]["type"] == "soft_health"
