"""Unit tests for Termux Handsets wire helpers (no device required)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

# Import module under test without stayturgid_shell connecting.
import stayturgid_handsets as th


def test_frame_pack():
    assert th._frame("ping") == b"\x00\x00\x00\x04ping"


def test_checked_flag_capital_k():
    assert th.Session._checked({"flags": "ckKfev"}) is True
    assert th.Session._checked({"flags": "ckfev"}) is False
    assert th.Session._checked({"checked": True}) is True


def test_center_bounds():
    assert th.Session._center({"bounds": [100, 200, 300, 400]}) == (200, 300)
    assert th.Session._center({}) is None


def test_center_for_rid(monkeypatch):
    class Fake(th.Session):
        def __init__(self):
            pass

        def _walk_nodes(self, data=None):
            return [{"rid": "android:id/button1", "bounds": [10, 20, 30, 40], "text": "ALLOW"}]

    s = Fake()
    assert s.center_for("resource-id", "android:id/button1") == (20, 30)
    assert s.center_for("text", "ALLOW") == (20, 30)


def test_dump_text_includes_rid(monkeypatch):
    class Fake(th.Session):
        def __init__(self):
            pass

        def dump(self):
            return {
                "root": {
                    "rid": "com.aurora.store:id/nav_host_fragment",
                    "text": "Apps",
                    "children": [],
                }
            }

    assert "nav_host_fragment" in Fake().dump_text()
    assert "Apps" in Fake().dump_text()


def test_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("STAYTURGID_HANDSETS", "0")
    assert th.enabled() is False
    monkeypatch.setenv("STAYTURGID_HANDSETS", "1")
    monkeypatch.setenv("STAYTURGID_NO_LOCAL_ADB", "1")
    monkeypatch.setenv("STAYTURGID_PEER_BOOTSTRAP", "0")
    monkeypatch.setattr(th.sh, "privileged_shell_expected", lambda: False)
    assert th.enabled() is False


def test_session_refcount_defers_stop(monkeypatch):
    """Nested Session: only last exit stops the daemon (L5)."""
    th._session_refs.clear()
    starts = []
    stops = []
    monkeypatch.setattr(th, "available", lambda: True)
    monkeypatch.setattr(th, "start", lambda port: starts.append(port))
    monkeypatch.setattr(th, "stop", lambda port: stops.append(port))
    monkeypatch.setattr(th, "_peer_bootstrap_enabled", lambda: False)
    monkeypatch.delenv("STAYTURGID_HANDSETS_KEEP", raising=False)

    outer = th.Session(port=9012)
    outer.__enter__()
    assert starts == [9012]
    inner = th.Session(port=9012)
    inner.__enter__()
    assert starts == [9012]  # no second start
    inner.__exit__(None, None, None)
    assert stops == []  # outer still holds ref
    outer.__exit__(None, None, None)
    assert stops == [9012]


def test_session_keep_env_skips_stop(monkeypatch):
    th._session_refs.clear()
    stops = []
    monkeypatch.setattr(th, "available", lambda: True)
    monkeypatch.setattr(th, "start", lambda port: None)
    monkeypatch.setattr(th, "stop", lambda port: stops.append(port))
    monkeypatch.setattr(th, "_peer_bootstrap_enabled", lambda: False)
    monkeypatch.setenv("STAYTURGID_HANDSETS_KEEP", "1")
    s = th.Session(port=9013)
    s.__enter__()
    s.__exit__(None, None, None)
    assert stops == []
