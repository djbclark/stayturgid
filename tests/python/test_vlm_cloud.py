"""Unit tests for control/lib/vlm_cloud.py (no live network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control" / "lib"))
import vlm_cloud as cloud  # noqa: E402


def test_load_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cloud, "GEMINI_ENV", tmp_path / "gemini.env")
    monkeypatch.setattr(cloud, "ANTHROPIC_ENV", tmp_path / "anthropic.env")
    monkeypatch.setattr(cloud, "COMBINED_ENV", tmp_path / "vlm-cloud.env")
    (tmp_path / "gemini.env").write_text("GEMINI_API_KEY=test-gemini-key\n")
    (tmp_path / "anthropic.env").write_text("ANTHROPIC_API_KEY=test-claude-key\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cloud.load_cloud_keys()
    assert cloud.gemini_key() == "test-gemini-key"
    assert cloud.anthropic_key() == "test-claude-key"


def test_parse_json_blob_fence():
    assert cloud._parse_json_blob('```json\n{"ok": true, "confidence": 0.9}\n```') == {
        "ok": True,
        "confidence": 0.9,
    }


def test_backends_available_auto(monkeypatch):
    monkeypatch.setenv("STAYTURGID_VLM_CLOUD", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    # Avoid file load overwriting
    monkeypatch.setattr(cloud, "load_cloud_keys", lambda: None)
    assert cloud.backends_available() == ["gemini", "claude"]


def test_ask_cloud_prefers_parsed(monkeypatch, tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    monkeypatch.setattr(cloud, "backends_available", lambda: ["gemini", "claude"])
    monkeypatch.setattr(
        cloud,
        "ask_gemini",
        lambda *a, **k: ("not json", None),
    )
    monkeypatch.setattr(
        cloud,
        "ask_claude",
        lambda *a, **k: ('{"ok":true,"confidence":0.9}', {"ok": True, "confidence": 0.9}),
    )
    raw, parsed, backend = cloud.ask_cloud(img, "prompt")
    assert backend == "claude"
    assert parsed and parsed["ok"] is True
