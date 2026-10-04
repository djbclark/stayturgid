"""Unit tests for control/bin/fire_peer_help.py ForceCommand parsing."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))

import fire_peer_help as fph


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


# --- unanswered ADB authorisation dialog (ShizukuTendCF AUTH_UNANSWERED) ---

import subprocess  # noqa: E402

import pytest  # noqa: E402

DEVICE_PY = REPO / "device" / "termux" / "py"
if str(DEVICE_PY) not in sys.path:
    sys.path.insert(0, str(DEVICE_PY))

import stayturgid_peer_help as sph  # noqa: E402


def _fake_shell(status_out, calls):
    def shell(target, cmd, timeout=30):
        calls.append(cmd)
        if "HEADLESS_STATUS" in cmd:
            return subprocess.CompletedProcess(cmd, 0, status_out, "")
        if cmd.startswith("pm path"):
            return subprocess.CompletedProcess(cmd, 0, "package:/data/app/x/base.apk\n", "")
        if cmd.startswith("pgrep"):
            return subprocess.CompletedProcess(cmd, 0, "up\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return shell


@pytest.mark.parametrize("mod", [fph, sph], ids=["mac", "device"])
def test_shizuku_start_stands_down_when_dialog_unanswered(mod, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(mod, "_ensure_connected", lambda target, timeout=20: None)
    monkeypatch.setattr(
        mod, "_shell", _fake_shell('Broadcast completed: result=3, data="STOPPED AUTH_UNANSWERED"', calls)
    )
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    assert mod.cmd_shizuku_start("192.0.2.13:5555") == mod.EXIT_AUTH_UNANSWERED == 3
    assert not any("libshizuku" in c or "start.sh" in c for c in calls)
    assert not any("force" in c for c in calls)
    assert mod.SHIZUKU_START_WITHHELD_MSG in capsys.readouterr().out


@pytest.mark.parametrize("mod", [fph, sph], ids=["mac", "device"])
def test_shizuku_start_unchanged_on_builds_without_marker(mod, monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "_ensure_connected", lambda target, timeout=20: None)
    # result=4 from STATUS is CRASHED, not the marker.
    monkeypatch.setattr(mod, "_shell", _fake_shell("Broadcast completed: result=4", calls))
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    assert mod.cmd_shizuku_start("192.0.2.13:5555") == 0
    status_at = next(i for i, c in enumerate(calls) if "HEADLESS_STATUS" in c)
    start_at = next(i for i, c in enumerate(calls) if "libshizuku" in c)
    assert status_at < start_at
