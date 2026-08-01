"""Unit tests for native-agent start script."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "control" / "tools" / "native-agent" / "start_agent.py"
SPEC = importlib.util.spec_from_file_location("start_agent", MODULE_PATH)
assert SPEC and SPEC.loader
start_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start_agent)


def test_start_agent_uses_headless_receiver_without_stopping_app(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_adb(serial, *args):
        cmd = ["adb", "-s", serial, *args]
        calls.append(cmd)
        if "pm path" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="package:org.stayturgid.agent.debug\n", stderr="")
        if "pidof org.stayturgid.agent.debug" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="101\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="OK\n", stderr="")

    monkeypatch.setattr(start_agent.adb, "resolve_target", lambda t: t)
    monkeypatch.setattr(start_agent.adb, "adb", fake_adb)
    monkeypatch.setattr(start_agent.time, "sleep", lambda _s: None)

    exit_code = start_agent.main(["s24"])
    assert exit_code == 0
    shell_commands = [call[-1] for call in calls if len(call) >= 5 and call[-2] == "shell"]
    assert (
        "am broadcast --include-stopped-packages "
        "-a org.stayturgid.agent.action.PEER_START_NOW "
        "-n org.stayturgid.agent.debug/org.stayturgid.agent.PeerStartReceiver"
    ) in shell_commands
    assert not any("am start" in command or "force-stop" in command or "kill " in command for command in shell_commands)
