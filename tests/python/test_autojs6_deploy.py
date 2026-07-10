"""Unit tests for control/tools/autojs6/deploy.py clean push + verify."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "control" / "tools" / "autojs6"))
sys.path.insert(0, str(REPO / "control" / "lib"))
sys.path.insert(
    0,
    str(REPO / "ansible_collections" / "stayturgid" / "android_common" / "plugins" / "module_utils"),
)

import autojs6_deploy_util as deploy_util  # noqa: E402
import deploy as deploy_mod  # noqa: E402


def test_deploy_wipes_lib_scripts_before_push(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("//")
    (proj / "lib" / "shizuku_shell.js").write_text("//")
    (proj / "lib" / "comonitor.js").write_text("//")
    (proj / "scripts" / "shizuku-probe.js").write_text("//")

    calls: list[str] = []

    def fake_resolve(alias):
        return "SERIAL"

    def fake_run_command(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "shizuku_shell.js" in joined and "test -f" in joined:
            return 0, "", ""
        return 0, "", ""

    monkeypatch.setattr(deploy_mod, "REPO_ROOT", root)
    monkeypatch.setattr(deploy_mod.adb, "resolve_target", fake_resolve)
    monkeypatch.setattr(deploy_mod, "_run_command", fake_run_command)
    monkeypatch.setattr(deploy_mod.adb_shell, "adb_connect", lambda *a, **k: None)

    assert deploy_mod.deploy_project("hd8") == 0

    wipe = [c for c in calls if "rm -rf" in c]
    assert wipe, "expected shell wipe"
    assert "/lib" in wipe[0] and "/scripts" in wipe[0]
    assert "mkdir" not in " ".join(calls)
    pushes = [c for c in calls if " push " in c]
    assert any("/lib" in c for c in pushes)
    assert any("/scripts" in c for c in pushes)
    verify = [c for c in calls if "shizuku_shell.js" in c and "test -f" in c]
    assert verify, "expected post-push file check"


def test_deploy_fails_when_verify_missing(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("//")
    (proj / "lib" / "shizuku_shell.js").write_text("//")
    (proj / "lib" / "comonitor.js").write_text("//")
    (proj / "scripts" / "shizuku-probe.js").write_text("//")

    def fake_run_command(cmd):
        joined = " ".join(cmd)
        if "shizuku_shell.js" in joined and "test -f" in joined:
            return 1, "", ""
        return 0, "", ""

    monkeypatch.setattr(deploy_mod, "REPO_ROOT", root)
    monkeypatch.setattr(deploy_mod.adb, "resolve_target", lambda a: "SERIAL")
    monkeypatch.setattr(deploy_mod, "_run_command", fake_run_command)
    monkeypatch.setattr(deploy_mod.adb_shell, "adb_connect", lambda *a, **k: None)
    assert deploy_mod.deploy_project("s24") == 1


def test_deploy_util_matches_default_target():
    assert deploy_util.DEFAULT_TARGET == "/sdcard/stayturgid/autojs6"


def test_project_src_dir_under_device_tree():
    root = "/path/to/stayturgid"
    assert deploy_util.project_src_dir(root).endswith(
        os.path.join("device", "autojs6")
    )
