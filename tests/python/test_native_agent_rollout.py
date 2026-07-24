"""Unit tests for strict native-agent rollout verification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "control" / "tools" / "native-agent" / "rollout.py"
SPEC = importlib.util.spec_from_file_location("native_agent_rollout", MODULE_PATH)
assert SPEC and SPEC.loader
rollout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollout)


def test_pids_filters_non_numeric_output() -> None:
    assert rollout._pids("123 456\nwarning") == ["123", "456"]
    assert rollout._pids(None) == []


def test_stop_stale_user_services_kills_every_pid(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=120, env=None):
        calls.append(cmd)
        stdout = "101 202\n" if any("pidof" in part for part in cmd) else ""
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(rollout, "_run", fake_run)
    monkeypatch.setattr(rollout.time, "sleep", lambda _seconds: None)

    assert rollout.stop_stale_user_services("serial") == ["101", "202"]
    assert calls[-1] == ["adb", "-s", "serial", "shell", "kill", "101", "202"]


def test_ensure_apk_passes_jdk_environment_to_build(tmp_path, monkeypatch) -> None:
    apk = tmp_path / "app-debug.apk"
    observed = {}

    def fake_run(cmd, timeout=120, env=None):
        observed["cmd"] = cmd
        observed["env"] = env
        apk.write_bytes(b"apk")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rollout, "APK", apk)
    monkeypatch.setattr(rollout, "_run", fake_run)

    assert rollout.ensure_apk() == apk
    assert observed["cmd"] == ["just", "agent-assemble"]
    assert observed["env"] is not None
