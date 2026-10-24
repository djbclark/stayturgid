"""Unit tests for control/bin/check_apk_updates.py."""

from __future__ import annotations

import importlib.util
import json
import logging
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

# cau's own import of control.lib.hermes_notify (for its sys.path setup) has
# already run by this point, so this import needs no path manipulation here.
from control.lib import hermes_notify  # noqa: E402


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
    monkeypatch.setattr(cau, "resolve_target", lambda route: "telegram:838808636:44130")

    sent: dict[str, list[str]] = {}
    monkeypatch.setattr(cau.subprocess, "run", lambda args, **kw: sent.setdefault("args", args))

    cau.main()

    assert "djbclark/stayturgid" not in checked
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert state["updates"], "expected at least one mismatched pinned APK"
    assert "args" in sent
    assert sent["args"][:3] == ["hermes", "send", "-t"]
    assert sent["args"][3] == "telegram:838808636:44130"


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


# --- change detection (no re-nag for an unchanged pending set) -----------------


def _patch_notifier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[list[str], Path]:
    """Point the checker at a tmp state file; record hermes_notify calls."""
    state_path = tmp_path / "apk-updates.json"
    monkeypatch.setattr(cau, "STATE_PATH", str(state_path))
    sent: list[str] = []
    monkeypatch.setattr(cau, "hermes_notify", lambda msg: sent.append(msg))
    return sent, state_path


def test_normalize_updates_sorts_and_dedups() -> None:
    assert cau.normalize_updates(["b: 1 -> 2", "a: 1 -> 2", "b: 1 -> 2"]) == ["a: 1 -> 2", "b: 1 -> 2"]


def test_load_last_updates_tolerates_missing_corrupt_and_unsorted(tmp_path: Path) -> None:
    assert cau.load_last_updates(str(tmp_path / "missing.json")) == []

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    assert cau.load_last_updates(str(corrupt)) == []

    odd = tmp_path / "odd.json"
    odd.write_text(json.dumps({"updates": ["b: 1 -> 2", 3, "a: 1 -> 2", "b: 1 -> 2"]}))
    assert cau.load_last_updates(str(odd)) == ["a: 1 -> 2", "b: 1 -> 2"]


def test_main_sends_on_first_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent, state_path = _patch_notifier(monkeypatch, tmp_path)
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: "v2.0.0")

    cau.main()

    assert len(sent) == 1
    assert "Stayturgid pinned APK updates available" in sent[0]
    assert "-> v2.0.0" in sent[0]
    state = json.loads(state_path.read_text())
    assert state["updates"]


def test_main_no_resend_when_pending_set_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sent, state_path = _patch_notifier(monkeypatch, tmp_path)
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: "v2.0.0")

    cau.main()
    assert len(sent) == 1

    cau.main()

    assert len(sent) == 1, "unchanged pending set must not re-notify"
    # The pending set is still printed to stdout for the Jobber log.
    out = capsys.readouterr().out
    assert "Stayturgid pinned APK updates available" in out
    assert "-> v2.0.0" in out
    state = json.loads(state_path.read_text())
    assert state["updates"]


def test_main_resends_when_latest_tag_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent, _state_path = _patch_notifier(monkeypatch, tmp_path)
    latest = {"tag": "v2.0.0"}
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: latest["tag"])

    cau.main()
    assert len(sent) == 1
    assert "-> v2.0.0" in sent[0]

    latest["tag"] = "v3.0.0"
    cau.main()

    assert len(sent) == 2
    assert "-> v3.0.0" in sent[1]
    assert "v2.0.0" not in sent[1]


def test_main_no_send_when_empty_on_first_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent, state_path = _patch_notifier(monkeypatch, tmp_path)
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: None)

    cau.main()

    assert sent == []
    state = json.loads(state_path.read_text())
    assert state["updates"] == []


def test_main_notifies_once_when_updates_clear_then_stays_quiet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent, state_path = _patch_notifier(monkeypatch, tmp_path)
    latest: dict[str, str | None] = {"tag": "v2.0.0"}
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: latest["tag"])

    cau.main()
    assert len(sent) == 1 and "available" in sent[0]

    # Pins caught up / GitHub unreachable: nothing pending any more.
    latest["tag"] = None
    cau.main()

    assert len(sent) == 2
    assert "cleared" in sent[1]
    state = json.loads(state_path.read_text())
    assert state["updates"] == []

    cau.main()
    assert len(sent) == 2, "empty -> empty is not a change"


def test_main_corrupt_state_treated_as_first_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent, state_path = _patch_notifier(monkeypatch, tmp_path)
    monkeypatch.setattr(cau, "latest_tag_for", lambda gh_repo: "v2.0.0")
    state_path.write_text("{not json")

    cau.main()

    assert len(sent) == 1
    state = json.loads(state_path.read_text())
    assert state["updates"]


# --- route resolution via the inbox register (control/lib/hermes_notify) -------


def test_hermes_route_resolves_from_register_fixture(tmp_path: Path) -> None:
    """A fixture site dir stands in for the real site-djbclark checkout, so this
    route resolves deterministically without the register having landed yet."""
    site_dir = tmp_path / "site-djbclark"
    registry_dir = site_dir / "registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / "telegram-inbox.env").write_text("INBOX_ROUTE_STAYTURGID_APK_UPDATES=telegram:838808636:44130\n")

    target = cau.resolve_target(cau.HERMES_ROUTE, site_dir=site_dir)

    assert target == "telegram:838808636:44130"


def test_hermes_route_falls_back_when_register_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A site dir with no registry env file must not silence the ping."""
    site_dir = tmp_path / "site-djbclark-no-registry"
    site_dir.mkdir()

    with caplog.at_level(logging.WARNING, logger=hermes_notify.logger.name):
        target = cau.resolve_target(cau.HERMES_ROUTE, site_dir=site_dir)

    assert target == hermes_notify.FALLBACK_TARGET
    assert any("fallback" in record.message for record in caplog.records)


def test_hermes_route_falls_back_when_route_missing_from_register(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An env file that exists but has no entry for this route also falls back."""
    site_dir = tmp_path / "site-djbclark"
    registry_dir = site_dir / "registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / "telegram-inbox.env").write_text("INBOX_ROUTE_SOME_OTHER_ROUTE=telegram:838808636:99999\n")

    with caplog.at_level(logging.WARNING, logger=hermes_notify.logger.name):
        target = cau.resolve_target(cau.HERMES_ROUTE, site_dir=site_dir)

    assert target == hermes_notify.FALLBACK_TARGET
    assert any("fallback" in record.message for record in caplog.records)


def test_hermes_notify_sends_to_resolved_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """check_apk_updates.hermes_notify() must use the route-resolved target, not a literal."""
    monkeypatch.setattr(cau, "resolve_target", lambda route: "telegram:838808636:44130")
    sent: dict[str, list[str]] = {}
    monkeypatch.setattr(cau.subprocess, "run", lambda args, **kw: sent.setdefault("args", args))

    cau.hermes_notify("a message")

    assert sent["args"] == ["hermes", "send", "-t", "telegram:838808636:44130", "a message"]
