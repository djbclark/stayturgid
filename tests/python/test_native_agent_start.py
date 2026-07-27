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


def test_start_agent_kills_stale_user_services(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_adb(serial, *args):
        cmd = ["adb", "-s", serial, *args]
        calls.append(cmd)
        if "pm path" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="package:org.stayturgid.agent.debug\n", stderr="")
        if "pidof org.stayturgid.agent.debug:userservice" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="301 302\n", stderr="")
        if "pidof org.stayturgid.agent:userservice" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="\n", stderr="")
        if "pidof org.stayturgid.agent.debug" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="101\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="OK\n", stderr="")

    monkeypatch.setattr(start_agent.adb, "resolve_target", lambda t: t)
    monkeypatch.setattr(start_agent.adb, "adb", fake_adb)
    monkeypatch.setattr(start_agent.time, "sleep", lambda _s: None)

    exit_code = start_agent.main(["s24"])
    assert exit_code == 0
    kill_calls = [call for call in calls if any("kill" in part for part in call)]
    assert len(kill_calls) == 1
    assert kill_calls[0] == ["adb", "-s", "s24", "shell", "kill 301 302"]
