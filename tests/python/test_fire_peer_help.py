"""Unit tests for control/bin/fire_peer_help.py ForceCommand parsing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import fire_peer_help as fph
import stayturgid_peer_help as dph


def test_ssh_original_parses_verb(monkeypatch):
    monkeypatch.setenv(
        "SSH_ORIGINAL_COMMAND",
        "handsets-start --target 192.0.2.13:5555 --port 9012",
    )
    seen = {}

    def fake(verb, target, port):
        seen["v"] = verb
        seen["t"] = target
        seen["p"] = port
        return 0

    monkeypatch.setattr(fph, "run_verb", fake)
    assert fph.main([]) == 0
    assert seen == {"v": "handsets-start", "t": "192.0.2.13:5555", "p": 9012}


def test_ssh_original_denies_empty(monkeypatch):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "")
    # Empty falls through to argparse — need argv
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    # Without SSH_ORIGINAL and without argv, argparse fails
    try:
        fph.main([])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def _fake_target(calls, installed=True, starts=True):
    """adb shell on a target whose Shizuku reports the unanswered-dialog marker."""
    alive = {"up": False}

    def shell(target, cmd, timeout=30):
        calls.append(cmd)
        out = ""
        if "HEADLESS_STATUS" in cmd:
            out = 'Broadcast completed: result=3, data="STOPPED AUTH_UNANSWERED"'
        elif cmd.startswith("pm path"):
            out = "package:/data/app/~~a==/moe.shizuku.privileged.api-b==/base.apk\n" if installed else ""
        elif "libshizuku.so" in cmd:
            alive["up"] = starts
            out = "" if starts else "starter: boom"
        elif cmd.startswith("pgrep"):
            out = "up\n" if alive["up"] else ""
        return subprocess.CompletedProcess(["adb"], 0, out, "")

    return shell


@pytest.mark.parametrize("module", [fph, dph], ids=["mac", "device"])
def test_shizuku_start_runs_the_starter_regardless_of_marker(monkeypatch, module, capsys):
    # The starter runs from an already-authorised adb shell: it offers no key,
    # so an unanswered Shizuku dialog must not stop it.
    calls = []
    monkeypatch.setattr(module, "_ensure_connected", lambda target, timeout=20: None)
    monkeypatch.setattr(module, "_shell", _fake_target(calls))
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    assert module.cmd_shizuku_start("192.0.2.13:5555") == 0
    assert any("libshizuku.so" in c for c in calls)
    assert not any("HEADLESS_STATUS" in c or "HEADLESS_START" in c for c in calls)
    assert "OK shizuku_server target=192.0.2.13:5555" in capsys.readouterr().out


def test_device_shizuku_start_failure_messages_unchanged(monkeypatch, capsys):
    monkeypatch.setattr(dph, "_ensure_connected", lambda target, timeout=20: None)
    monkeypatch.setattr(dph.time, "sleep", lambda _s: None)
    monkeypatch.setattr(dph, "_shell", _fake_target([], installed=False))
    assert dph.cmd_shizuku_start("t:5555") == 1
    assert "FAIL Shizuku not installed" in capsys.readouterr().err
    monkeypatch.setattr(dph, "_shell", _fake_target([], starts=False))
    assert dph.cmd_shizuku_start("t:5555") == 1
    assert "FAIL shizuku start: starter: boom" in capsys.readouterr().err


def test_start_shizuku_native_takes_any_authorised_shell(monkeypatch):
    calls = []
    fake = _fake_target(calls)
    monkeypatch.setattr(dph.time, "sleep", lambda _s: None)

    def shell(cmd, timeout):
        r = fake("localhost:5555", cmd, timeout)
        return r.returncode, r.stdout, r.stderr

    assert dph.start_shizuku_native(shell) == (True, "")
    assert [c.split()[0] for c in calls] == ["pm", "test", "pgrep"]
