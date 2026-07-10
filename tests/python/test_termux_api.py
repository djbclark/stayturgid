"""Unit tests for control/lib/termux_api.py (no device)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import termux_api as tapi  # noqa: E402


def test_is_termux_api():
    assert tapi.is_termux_api(["termux-notification", "--id", "x"])
    assert tapi.is_termux_api(["/data/data/com.termux/files/usr/bin/termux-torch", "on"])
    assert not tapi.is_termux_api(["adb", "shell", "echo"])


def test_is_fire_and_forget():
    assert tapi.is_fire_and_forget(["termux-toast", "hi"])
    assert tapi.is_fire_and_forget(["termux-notification-remove", "x"])
    assert not tapi.is_fire_and_forget(["termux-dialog", "confirm"])
    assert not tapi.is_fire_and_forget(["termux-battery-status"])


def test_run_timeout_does_not_kill(monkeypatch):
    killed = []

    class FakeTimeout(subprocess.TimeoutExpired):
        def __init__(self):
            super().__init__(cmd="termux-toast", timeout=1)
            self.pid = 4242

    def boom(*_a, **_k):
        raise FakeTimeout()

    monkeypatch.setattr(tapi.subprocess, "run", boom)
    monkeypatch.setattr(
        tapi.os,
        "killpg",
        lambda *a, **k: killed.append(a) or (_ for _ in ()).throw(AssertionError("must not kill")),
    )
    # Even if killpg existed on the module path, run() must not call it.
    assert tapi.run(["termux-toast", "x"], timeout=1) is None
    assert killed == []


def test_run_ff_orphans_on_timeout(monkeypatch):
    class FakeProc:
        returncode = 0

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="termux-torch", timeout=timeout)

    monkeypatch.setattr(
        tapi.subprocess,
        "Popen",
        lambda *a, **k: FakeProc(),
    )
    r = tapi.run_ff(["termux-torch", "on"], timeout=0.01)
    assert r is not None
    assert r.returncode == 0
