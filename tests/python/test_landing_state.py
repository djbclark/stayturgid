"""Tests for the landing catalog/runtime-state split."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.landing import discover, state  # noqa: E402


def test_first_use_migrates_legacy_observations(tmp_path, monkeypatch):
    catalog = tmp_path / "services.json"
    runtime = tmp_path / "config" / "services.json"
    catalog.write_text(
        json.dumps({"hidden": [], "services": [{"url": "http://example", "label": "Example", "group": "mac"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(state, "CATALOG_FILE", catalog)
    monkeypatch.setattr(state, "STATE_FILE", runtime)

    migrated = state.load_state()

    assert migrated["services"][0]["url"] == "http://example"
    assert json.loads(runtime.read_text(encoding="utf-8")) == migrated
    assert json.loads(catalog.read_text(encoding="utf-8"))["services"][0].keys() == {
        "url", "label", "group"
    }


def test_discovery_writes_runtime_state_not_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "services.json"
    runtime = tmp_path / "config" / "services.json"
    catalog.write_text(
        json.dumps({"hidden": [], "services": [{"url": "http://example", "label": "Example", "group": "mac"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(state, "CATALOG_FILE", catalog)
    monkeypatch.setattr(state, "STATE_FILE", runtime)
    monkeypatch.setattr(discover, "KNOWN_SERVICES", state.load_catalog()["services"])
    monkeypatch.setattr(discover, "_scan_localhost", lambda: [])
    monkeypatch.setattr(discover, "_http_probe", lambda _url: 200)

    before = catalog.read_text(encoding="utf-8")
    result = discover.discover()

    assert result["services"][0]["status_code"] == 200
    assert catalog.read_text(encoding="utf-8") == before
    assert runtime.is_file()
