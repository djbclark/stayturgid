"""Unit tests for control/lib/adb_cli.py."""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
import adb_cli as ac


def test_adb_builds_serial_scoped_argv(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    ac.adb("192.0.2.12:5555", "shell", "true", check=False)
    assert seen["cmd"] == ["adb", "-s", "192.0.2.12:5555", "shell", "true"]
    assert seen["kwargs"]["check"] is False


def test_alias_for_host_forwards_to_stayturgid_device(monkeypatch):
    seen = {}

    def fake_alias_for_host(host):
        seen["host"] = host
        return "hd8"

    monkeypatch.setattr(ac.dev, "alias_for_host", fake_alias_for_host)
    assert ac.alias_for_host("100.124.55.39") == "hd8"
    assert seen["host"] == "100.124.55.39"


def test_debugging_dialog_present_detects_usb_activity(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="...UsbDebuggingActivity...", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is True


def test_debugging_dialog_present_detects_wifi_activity(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="...WifiDebuggingActivity...", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is True


def test_debugging_dialog_present_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="nothing interesting", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is False


def test_debugging_dialog_present_never_sends_keyevents(monkeypatch):
    """The old dismiss function sent 'input keyevent' — the detector must never do this."""
    sent = []

    def fake_run(cmd, **kwargs):
        sent.append(cmd)
        return subprocess.CompletedProcess([], 0, stdout="...WifiDebuggingActivity...", stderr="")

    monkeypatch.setattr(ac, "run", fake_run)
    ac.debugging_dialog_present("serial")
    assert not any("keyevent" in part for cmd in sent for part in cmd)


def fake_phone(monkeypatch, inversion_turns_on):
    """run() stand-in for a phone showing the 16 KB dialog until OK is pressed while inverted."""
    state = {"inv": "0", "dialog": True}
    sent = []

    def fake_run(cmd, **kwargs):
        sent.append(cmd)
        out = ""
        if cmd[4:7] == ["settings", "put", "secure"]:
            state["inv"] = cmd[-1] if cmd[-1] != "1" or inversion_turns_on else state["inv"]
        elif cmd[4:7] == ["settings", "get", "secure"]:
            out = state["inv"] + "\n"
        elif "KEYCODE_ENTER" in cmd:
            state["dialog"] = state["inv"] != "1"
        elif "dumpsys" in cmd and state["dialog"]:
            out = "...AppCompatibilityDialog..."
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    monkeypatch.setattr(ac.time, "sleep", lambda _s: None)
    return state, sent


def test_dismiss_app_compatibility_dialog_presses_ok_only_while_inverted(monkeypatch):
    state, sent = fake_phone(monkeypatch, inversion_turns_on=True)
    assert ac.dismiss_app_compatibility_dialog("serial") is True
    assert state["dialog"] is False
    assert state["inv"] == "0"  # restored to what it was


def test_dismiss_app_compatibility_dialog_refuses_without_inversion(monkeypatch):
    state, sent = fake_phone(monkeypatch, inversion_turns_on=False)
    assert ac.dismiss_app_compatibility_dialog("serial") is False
    assert state["dialog"] is True
    assert not any("keyevent" in part for cmd in sent for part in cmd)
