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


# ---------------------------------------------------------------------------
# stayturgid#310: the nightly Termux pkg upgrade's failures used to reach only a
# local log file, so a run of failures was invisible off-host. These assert the
# writer half of the pipeline -- the Vector `file` source tails exactly the path
# termux_pkg_path() returns, so a drift between them silently ships nothing.
# ---------------------------------------------------------------------------


def test_termux_pkg_path_is_created_empty_so_vector_can_attach(tmp_path, monkeypatch):
    """Vector's file source must be able to attach before the first failure."""
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    path = stats.termux_pkg_path()

    assert path == tmp_path / "stats" / "termux_pkg.jsonl"
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == ""


def test_record_termux_pkg_error_writes_one_queryable_line(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    stats.record_termux_pkg_error("upgrade", "ssh connect timed out", host="hd8", rc=1)

    rows = _read_jsonl(tmp_path / "stats" / "termux_pkg.jsonl")
    assert len(rows) == 1
    row = rows[0]
    # Each field is one the remap promotes for OpenObserve SQL.
    assert row["type"] == "termux_pkg_error"
    assert row["phase"] == "upgrade"
    assert row["host"] == "hd8"
    assert row["error"] == "ssh connect timed out"
    assert row["rc"] == 1
    assert row["ts"].endswith("Z")


def test_record_termux_pkg_error_appends_rather_than_truncating(tmp_path, monkeypatch):
    """Vector checkpoints byte offsets; a truncating writer would replay or lose."""
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    monkeypatch.setattr(stats, "STATS_DIR", tmp_path / "stats")

    stats.record_termux_pkg_error("lock", "fleet lock held", rc=3)
    stats.record_termux_pkg_error("upgrade", "rc=2 from ansible", rc=2)

    rows = _read_jsonl(tmp_path / "stats" / "termux_pkg.jsonl")
    assert [r["phase"] for r in rows] == ["lock", "upgrade"]


def test_record_termux_pkg_error_never_raises(tmp_path, monkeypatch):
    """Telemetry must not be able to break the upgrade job it reports on."""
    monkeypatch.setattr(stats, "ROOT", tmp_path)
    # Point STATS_DIR at a path that cannot be created: a child of a regular file.
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(stats, "STATS_DIR", blocker / "stats")

    stats.record_termux_pkg_error("upgrade", "boom", rc=1)  # must not raise


def test_the_nightly_job_records_every_failure_path(tmp_path):
    """A failure path that only logs is the bug #310 describes. Guard all of them."""
    src = (REPO / "control/bin/termux_pkg_nightly.py").read_text(encoding="utf-8")
    assert "from control.lib.stats import record_termux_pkg_error" in src
    # Every `return` that signals failure should be preceded by a record call.
    assert src.count("record_termux_pkg_error(") >= 6, (
        "a failure path in termux_pkg_nightly.py logs without recording telemetry"
    )
    for phase in ('"preflight"', '"lock"', '"upgrade"'):
        assert f"record_termux_pkg_error({phase}" in src
