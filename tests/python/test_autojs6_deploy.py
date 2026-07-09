"""Unit tests for autojs6/mac/deploy.py clean push + verify."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "autojs6" / "mac"))
sys.path.insert(0, str(REPO / "shared" / "mac"))

import deploy as deploy_mod  # noqa: E402


def test_deploy_wipes_lib_scripts_before_push(monkeypatch):
    calls: list[tuple] = []

    def fake_resolve(alias):
        return "SERIAL"

    def fake_adb(serial, *args, check=True):
        calls.append((serial, args, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy_mod.adb, "resolve_target", fake_resolve)
    monkeypatch.setattr(deploy_mod.adb, "adb", fake_adb)

    assert deploy_mod.deploy_project("hd8") == 0

    shell_cmds = [c[1] for c in calls if c[1] and c[1][0] == "shell"]
    assert shell_cmds, "expected shell wipe"
    wipe = shell_cmds[0][1]
    assert "rm -rf" in wipe and "/lib" in wipe and "/scripts" in wipe
    assert "mkdir" not in wipe

    pushes = [c[1] for c in calls if c[1] and c[1][0] == "push"]
    assert any(str(p[1]).endswith("/lib") and str(p[2]).endswith("/lib") for p in pushes)
    assert any(str(p[1]).endswith("/scripts") and str(p[2]).endswith("/scripts") for p in pushes)

    verify = [c for c in calls if c[1] and c[1][0] == "shell" and "shizuku_shell.js" in c[1][1]]
    assert verify, "expected post-push file check"


def test_deploy_fails_when_verify_missing(monkeypatch):
    def fake_adb(serial, *args, check=True):
        joined = " ".join(str(a) for a in args)
        if "shizuku_shell.js" in joined:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy_mod.adb, "resolve_target", lambda a: "SERIAL")
    monkeypatch.setattr(deploy_mod.adb, "adb", fake_adb)
    assert deploy_mod.deploy_project("s24") == 1
