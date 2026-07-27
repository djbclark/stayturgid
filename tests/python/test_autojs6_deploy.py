"""Unit tests for control/tools/autojs6/deploy.py clean push + verify."""

from __future__ import annotations

import os
import subprocess
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

import autojs6_deploy_util as deploy_util
import deploy as deploy_mod


def test_deploy_wipes_lib_scripts_before_push(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("//")
    (proj / "fleet_profile.json").write_text("{}")
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

    assert deploy_mod.deploy_project("fireos-device") == 0

    wipe = [c for c in calls if "rm -rf" in c]
    assert wipe, "expected shell wipe"
    assert "/lib" in wipe[0] and "/scripts" in wipe[0]
    assert "mkdir" not in " ".join(calls)
    pushes = [c for c in calls if " push " in c]
    assert any("/lib" in c for c in pushes)
    assert any("/scripts" in c for c in pushes)
    verify = [c for c in calls if "shizuku_shell.js" in c and "test -f" in c]
    assert verify, "expected post-push file check"


def test_deploy_excludes_ts_source_files(monkeypatch, tmp_path):
    """Committed .ts source lives beside the compiled .js for git review/debug;
    Rhino only ever loads the .js (every require() uses an explicit .js
    extension). adb push must not ship .ts to the device — it serves no
    on-device purpose and would grow unbounded as more files migrate."""
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("//")
    (proj / "fleet_profile.json").write_text("{}")
    (proj / "lib" / "shizuku_shell.js").write_text("//")
    (proj / "lib" / "shizuku_shell.ts").write_text("// source")
    (proj / "lib" / "comonitor.js").write_text("//")
    (proj / "lib" / "comonitor.ts").write_text("// source")
    (proj / "scripts" / "shizuku-probe.js").write_text("//")
    (proj / "scripts" / "shizuku-probe.ts").write_text("// source")

    staged_dir_contents: dict[str, list[str]] = {}

    def fake_run_command(cmd):
        if len(cmd) >= 2 and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        if len(cmd) >= 5 and cmd[3] == "push":
            local = Path(cmd[4])
            if local.is_dir():
                staged_dir_contents[local.name] = sorted(p.name for p in local.rglob("*") if p.is_file())
        if "shizuku_shell.js" in " ".join(cmd) and "test -f" in " ".join(cmd):
            return 0, "", ""
        return 0, "", ""

    monkeypatch.setattr(deploy_mod, "REPO_ROOT", root)
    monkeypatch.setattr(deploy_mod.adb, "resolve_target", lambda a: "SERIAL")
    monkeypatch.setattr(deploy_mod, "_run_command", fake_run_command)
    monkeypatch.setattr(deploy_mod.adb_shell, "adb_connect", lambda *a, **k: None)

    assert deploy_mod.deploy_project("fireos-device") == 0

    assert "lib" in staged_dir_contents and "scripts" in staged_dir_contents
    for pushed_files in staged_dir_contents.values():
        assert not any(f.endswith(".ts") for f in pushed_files), pushed_files
    assert "shizuku_shell.js" in staged_dir_contents["lib"]
    assert "comonitor.js" in staged_dir_contents["lib"]
    assert "shizuku-probe.js" in staged_dir_contents["scripts"]

    # Staging dirs are scratch — must not leak into the real source tree or survive after push.
    assert not any((proj / "lib").glob("*.tmp*"))
    for pushed_files in staged_dir_contents.values():
        assert pushed_files, "staged dir should not be empty"


def test_deploy_fails_when_verify_missing(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("//")
    (proj / "fleet_profile.json").write_text("{}")
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
    assert deploy_mod.deploy_project("oneui-device") == 1


def test_deploy_util_matches_default_target():
    assert deploy_util.DEFAULT_TARGET == "/sdcard/stayturgid/autojs6"


def test_project_src_dir_under_device_tree():
    root = "/path/to/stayturgid"
    assert deploy_util.project_src_dir(root).endswith(os.path.join("device", "autojs6"))


def test_deploy_script_usage_works_standalone():
    result = subprocess.run(
        [sys.executable, str(REPO / "control" / "tools" / "autojs6" / "deploy.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
