"""Unit tests for control/bin/watch_battery_percent.py — the #16 evidence
capture diagnostic (see that module's docstring: this is not a fix, it's
attribution tooling for a bug no prior investigation could reproduce)."""

from __future__ import annotations

import json

import watch_battery_percent as wbp


def test_parse_setting_value_normal():
    assert wbp.parse_setting_value("1\n") == "1"
    assert wbp.parse_setting_value("0") == "0"


def test_parse_setting_value_null_variants():
    assert wbp.parse_setting_value(None) is None
    assert wbp.parse_setting_value("") is None
    assert wbp.parse_setting_value("null\n") is None
    assert wbp.parse_setting_value("NULL") is None


def test_battery_percent_hidden():
    assert wbp.battery_percent_hidden(None) is True
    assert wbp.battery_percent_hidden("0") is True
    assert wbp.battery_percent_hidden("1") is False


def test_extract_dumpsys_attribution_empty_on_missing_section():
    assert wbp.extract_dumpsys_attribution("") == []
    assert wbp.extract_dumpsys_attribution("no relevant lines here\n") == []


def test_extract_dumpsys_attribution_matches_key_and_pkg():
    text = (
        "Settings (0x0):\n"
        "  12-31 09:00:00.123 UPDATE system:status_bar_show_battery_percent "
        "value=0 default=null tag=null pkg=com.android.shell\n"
        "  12-31 09:00:01.456 UPDATE system:accelerometer_rotation "
        "value=1 pkg=com.android.systemui\n"
    )
    hits = wbp.extract_dumpsys_attribution(text)
    assert len(hits) == 1
    assert hits[0]["op"] == "UPDATE"
    assert hits[0]["pkg"] == "com.android.shell"


def test_extract_dumpsys_attribution_line_without_pkg_still_captured():
    text = "  12-31 09:00:00.123 UPDATE system:status_bar_show_battery_percent value=0\n"
    hits = wbp.extract_dumpsys_attribution(text)
    assert len(hits) == 1
    assert hits[0]["pkg"] is None
    assert "status_bar_show_battery_percent" in hits[0]["line"]


def test_build_evidence_record_unchanged():
    record = wbp.build_evidence_record("p7a", ["just", "deploy"], "1", "1", "", "")
    assert record["changed"] is False
    assert record["reset_to_hidden"] is False
    assert record["host"] == "p7a"
    assert record["command"] == ["just", "deploy"]
    # Must be JSON-serializable as-is (this is what gets written to disk).
    json.dumps(record)


def test_build_evidence_record_reset_to_hidden():
    record = wbp.build_evidence_record("p7a", ["just", "deploy"], "1", "0", "", "")
    assert record["changed"] is True
    assert record["reset_to_hidden"] is True


def test_build_evidence_record_changed_but_not_hidden():
    record = wbp.build_evidence_record("p7a", ["just", "deploy"], "0", "1", "", "")
    assert record["changed"] is True
    assert record["reset_to_hidden"] is False


def test_build_evidence_record_absent_after_counts_as_hidden():
    record = wbp.build_evidence_record("p7a", ["just", "deploy"], "1", None, "", "")
    assert record["changed"] is True
    assert record["reset_to_hidden"] is True


def test_main_requires_separator(capsys):
    rc = wbp.main(["p7a", "just", "deploy"])
    assert rc == 2


def test_main_requires_single_host_and_command(capsys):
    assert wbp.main(["--"]) == 2
    assert wbp.main(["p7a", "extra", "--", "cmd"]) == 2


def test_main_runs_command_and_writes_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(wbp, "OUT_DIR", tmp_path)
    monkeypatch.setattr(wbp.dev, "resolve_adb", lambda host: "127.0.0.1:5555")

    values = iter(["1", "0"])  # before, after
    monkeypatch.setattr(wbp, "_get_value", lambda serial: next(values))
    monkeypatch.setattr(wbp, "_get_dumpsys", lambda serial: "")

    calls = []
    monkeypatch.setattr(wbp.subprocess, "call", lambda cmd: calls.append(cmd) or 0)

    rc = wbp.main(["p7a", "--", "echo", "hi"])

    assert rc == 0
    assert calls == [["echo", "hi"]]
    written = list(tmp_path.glob("p7a-*.json"))
    assert len(written) == 1
    record = json.loads(written[0].read_text())
    assert record["before"] == "1"
    assert record["after"] == "0"
    assert record["reset_to_hidden"] is True
