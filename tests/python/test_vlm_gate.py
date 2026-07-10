"""Unit tests for shared/mac/vlm_gate.py (no llama-server required)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "mac"))

import vlm_gate as vlm  # noqa: E402


def test_vlm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("STAYTURGID_VLM", raising=False)
    monkeypatch.delenv("QSS_VLM", raising=False)
    assert vlm.vlm_enabled() is False


def test_vlm_enabled_env(monkeypatch):
    monkeypatch.setenv("STAYTURGID_VLM", "1")
    assert vlm.vlm_enabled() is True


def test_parse_json_blob_embedded():
    parsed = vlm._parse_json_blob('Sure. {"ok":true,"confidence":0.9,"notes":"x"}')
    assert parsed is not None
    assert parsed["ok"] is True


def test_verify_skipped_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_VLM", "0")
    shot = tmp_path / "x.png"
    shot.write_bytes(b"png")
    gate = vlm.VlmGate(autostart=False)
    ok, detail = gate.verify(shot, "play_autoupdate_dont")
    assert ok is True
    assert detail.get("skipped")


def test_verify_play_autoupdate_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_VLM", "1")
    shot = tmp_path / "x.png"
    shot.write_bytes(b"png")
    gate = vlm.VlmGate(autostart=False)
    gate.ready = True
    payload = {
        "choices": [{"message": {"content": json.dumps({
            "ok": True,
            "setting": "dont_auto_update",
            "confidence": 0.99,
            "notes": "selected",
        })}}]
    }

    def fake_urlopen(req, timeout=None):
        resp = MagicMock()
        if req.full_url.endswith("/health"):
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch.object(vlm, "prepare_image", return_value=shot):
        with patch.object(vlm.urllib.request, "urlopen", fake_urlopen):
            with patch.object(vlm, "_model_id", return_value="test-model"):
                ok, detail = gate.verify(shot, "play_autoupdate_dont")
    assert ok is True
    assert detail["confidence"] == 0.99


def test_verify_strict_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_VLM", "1")
    monkeypatch.setenv("STAYTURGID_VLM_STRICT", "1")
    shot = tmp_path / "x.png"
    shot.write_bytes(b"png")
    gate = vlm.VlmGate(autostart=False)
    gate.ready = False
    ok, detail = gate.verify(shot, "play_autoupdate_dont")
    assert ok is False
    assert detail.get("reason") == "vlm_unavailable" or detail.get("skipped")
