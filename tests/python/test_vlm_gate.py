"""Unit tests for control/lib/vlm_gate.py (no llama-server required)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

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
    # Host may have real cloud keys; isolate so "disabled" means no backends.
    monkeypatch.setenv("STAYTURGID_VLM_CLOUD", "off")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if vlm.cloud is not None:
        monkeypatch.setattr(vlm.cloud, "cloud_enabled", lambda: False)
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
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "ok": True,
                            "setting": "dont_auto_update",
                            "confidence": 0.99,
                            "notes": "selected",
                        }
                    )
                }
            }
        ]
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


def test_ensure_server_installs_launchd_when_missing(monkeypatch, tmp_path):
    plist = tmp_path / "homebrew.mxcl.ui-tars.plist"
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if "ansible-playbook" in cmd:
            plist.write_text("plist")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(vlm, "LAUNCHAGENT_PLIST", plist)
    monkeypatch.setattr(vlm, "MAC_SITE_PLAYBOOK", tmp_path / "mac-site.yml")
    monkeypatch.setattr(vlm.os, "uname", lambda: type("U", (), {"sysname": "Darwin"})())
    monkeypatch.setattr(vlm, "server_healthy", lambda: plist.is_file())
    monkeypatch.setattr(vlm.subprocess, "run", fake_run)
    assert vlm.ensure_server(start=True) is True
    assert calls[0][0] == "ansible-playbook"
    assert "vlm-service" in calls[0]


def test_ensure_server_kickstarts_launchd(monkeypatch, tmp_path):
    plist = tmp_path / "homebrew.mxcl.ui-tars.plist"
    plist.write_text("plist")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(vlm, "LAUNCHAGENT_PLIST", plist)
    monkeypatch.setattr(vlm, "MAC_SITE_PLAYBOOK", tmp_path / "mac-site.yml")
    monkeypatch.setattr(vlm.os, "uname", lambda: type("U", (), {"sysname": "Darwin"})())
    monkeypatch.setattr(vlm, "server_healthy", lambda: len(calls) > 0)
    monkeypatch.setattr(vlm.subprocess, "run", fake_run)
    assert vlm.ensure_server(start=True) is True
    assert calls[0][0] == "ansible-playbook"
    assert "agents-ensure" in calls[0]


def test_verify_strict_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_VLM", "1")
    monkeypatch.setenv("STAYTURGID_VLM_STRICT", "1")
    monkeypatch.setenv("STAYTURGID_VLM_CLOUD", "off")
    if vlm.cloud is not None:
        monkeypatch.setattr(vlm.cloud, "cloud_enabled", lambda: False)
    shot = tmp_path / "x.png"
    shot.write_bytes(b"png")
    gate = vlm.VlmGate(autostart=False)
    gate.ready = False
    gate.cloud_ready = False
    ok, detail = gate.verify(shot, "play_autoupdate_dont")
    assert ok is False
    assert detail.get("reason") == "vlm_unavailable" or detail.get("skipped")
