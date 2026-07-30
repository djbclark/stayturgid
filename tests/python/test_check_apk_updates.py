"""Unit tests for control/bin/check_apk_updates.py."""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_MOD = REPO / "control" / "bin" / "check_apk_updates.py"
_spec = importlib.util.spec_from_file_location("check_apk_updates", _MOD)
assert _spec is not None
cau = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(cau)


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


# --- latest_tag_for -----------------------------------------------------------


def test_latest_tag_for_uses_releases_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cau.urllib.request, "urlopen", lambda req: _FakeResponse({"tag_name": "v2.0.0"}))
    assert cau.latest_tag_for("some/repo") == "v2.0.0"


def test_latest_tag_for_falls_back_to_tags_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_urlopen(req):
        calls.append(req.full_url)
        if "/releases/latest" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)
        return _FakeResponse([{"name": "v3.1.0"}])

    monkeypatch.setattr(cau.urllib.request, "urlopen", fake_urlopen)
    assert cau.latest_tag_for("some/repo") == "v3.1.0"
    assert any("/tags" in c for c in calls)


def test_latest_tag_for_returns_none_on_non_404_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", None, None)

    monkeypatch.setattr(cau.urllib.request, "urlopen", fake_urlopen)
    assert cau.latest_tag_for("some/repo") is None


def test_latest_tag_for_returns_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req):
        raise OSError("network unreachable")

    monkeypatch.setattr(cau.urllib.request, "urlopen", fake_urlopen)
    assert cau.latest_tag_for("some/repo") is None


# --- main() --------------------------------------------------------------------


def test_main_skips_own_release_and_notifies_on_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "apk-updates.json"
    monkeypatch.setattr(cau, "STATE_PATH", str(state_path))

    checked = []

    def fake_latest_tag_for(gh_repo: str) -> str:
        checked.append(gh_repo)
        # djbclark/stayturgid backs org.stayturgid.agent, which must be
        # skipped — if it weren't, this deliberately-mismatched value would
        # show up as a false-positive "update" every run.
        if gh_repo == "djbclark/stayturgid":
            return "ops-v9.9.9"
        return "v999.999.999"

    monkeypatch.setattr(cau, "latest_tag_for", fake_latest_tag_for)

    sent = {}
    monkeypatch.setattr(cau.subprocess, "run", lambda args, **kw: sent.setdefault("args", args))

    cau.main()

    assert "djbclark/stayturgid" not in checked
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert state["updates"], "expected at least one mismatched pinned APK"
    assert "args" in sent
    assert sent["args"][:3] == ["hermes", "send", "-t"]
    assert sent["args"][3] == cau.HERMES_TARGET


def test_main_does_not_notify_when_everything_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "apk-updates.json"
    monkeypatch.setattr(cau, "STATE_PATH", str(state_path))
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: None)

    called = []
    monkeypatch.setattr(cau.subprocess, "run", lambda *a, **kw: called.append(a))

    cau.main()

    assert called == []
    state = json.loads(state_path.read_text())
    assert state["updates"] == []
