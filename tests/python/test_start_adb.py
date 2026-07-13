"""Unit tests for the Python Termux boot supervisor."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import start_adb  # noqa: E402


def test_shell_transport_prefers_localhost_adb(monkeypatch):
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: (0, "2000\n"))

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb"


def test_shell_transport_falls_back_to_rish(monkeypatch):
    responses = iter([(-1, ""), (0, "Entering shell...\n2000\n"), (0, "2000\n")])
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        start_adb, "_capture", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb-rish-recovered"


def test_launch_accepts_listener_after_client_timeout(monkeypatch):
    monkeypatch.setattr(
        start_adb, "_shell_run", lambda *args, **kwargs: (0, "localhost-adb")
    )
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: -1)
    monkeypatch.setattr(start_adb, "_firerpa_alive", lambda: True)
    monkeypatch.setattr(start_adb.time, "sleep", lambda *_: None)
    messages = []
    monkeypatch.setattr(start_adb, "_boot_log", messages.append)

    assert start_adb._launch_firerpa_via_shell("test") is True
    assert any("confirmed" in message for message in messages)


def test_launch_uses_accessibility_coexistence_lifecycle(monkeypatch):
    commands = []
    monkeypatch.setattr(
        start_adb, "_shell_run", lambda *args, **kwargs: (0, "localhost-adb")
    )
    monkeypatch.setattr(
        start_adb,
        "_run",
        lambda command, **_kwargs: commands.append(command) or 0,
    )
    messages = []
    monkeypatch.setattr(start_adb, "_boot_log", messages.append)

    assert start_adb._launch_firerpa_via_shell("test") is True
    assert commands[0][:2] == [sys.executable, start_adb.FIRERPA_LIFECYCLE]
    assert "--adb-target" in commands[0]
    assert "launch.sh" not in commands[0]
    assert any("accessibility coexistence" in message for message in messages)
