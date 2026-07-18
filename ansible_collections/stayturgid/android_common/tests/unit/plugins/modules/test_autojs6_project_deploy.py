"""Unit tests for autojs6_project_deploy module and deploy util."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import autojs6_deploy_util as deploy_util  # noqa: E402
import autojs6_project_deploy as mod  # noqa: E402


def _fake_run(cmd_results=None):
    def run_command(cmd, *args, **kwargs):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if "push" in joined:
            return (0, "", "")
        if "rm -rf" in joined:
            return (0, "", "")
        if "mkdir -p" in joined:
            return (0, "", "")
        if "shizuku_shell.js" in joined:
            return (0, "", "")
        return (0, "", "")

    return run_command


def _seed_project(tmp_path):
    root = tmp_path / "repo"
    proj = root / "device" / "autojs6"
    (proj / "lib").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    (proj / "project.json").write_text("{}")
    (proj / "main.js").write_text("// main")
    (proj / "fleet_profile.json").write_text("{}")
    (proj / "lib" / "shizuku_shell.js").write_text("//")
    (proj / "lib" / "comonitor.js").write_text("//")
    (proj / "scripts" / "shizuku-probe.js").write_text("//")
    return root


def test_deploy_util_wipes_before_push(tmp_path):
    root = _seed_project(tmp_path)
    calls = []

    def run_command(cmd, *args, **kwargs):
        joined = " ".join(cmd)
        calls.append(joined)
        return _fake_run()(cmd)

    ok, msg, changed = deploy_util.deploy_project(run_command, "SERIAL", str(root), target="/sdcard/stayturgid/autojs6")
    assert ok, msg
    assert changed is True
    wipe_idx = next(i for i, c in enumerate(calls) if "rm -rf" in c)
    push_idx = next(i for i, c in enumerate(calls) if " push " in c)
    assert wipe_idx < push_idx
    assert "mkdir" not in " ".join(calls)


def test_deploy_util_fails_verify(tmp_path):
    root = _seed_project(tmp_path)

    def run_command(cmd, *args, **kwargs):
        joined = " ".join(cmd)
        if "shizuku_shell.js" in joined:
            return (1, "", "missing")
        return _fake_run()(cmd)

    ok, msg, _changed = deploy_util.deploy_project(
        run_command, "SERIAL", str(root), target="/sdcard/stayturgid/autojs6"
    )
    assert not ok
    assert "incomplete" in msg


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        return _fake_run(cmd_results)(cmd)

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(1)),
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_module_deploy_project_and_device_json(mocker, tmp_path):
    root = _seed_project(tmp_path)
    device_json = tmp_path / "device.json"
    device_json.write_text('{"device":"fireos-device"}')
    out = run_module(
        mocker,
        dict(
            device="fireos-device",
            repo_root=str(root),
            target="/sdcard/stayturgid/autojs6",
            device_json=str(device_json),
            connect=False,
        ),
    )
    assert out["changed"] is True
    assert out["project_deployed"] is True
    assert out["device_json_pushed"] is True


def test_module_check_mode_reports_changed(mocker, tmp_path):
    root = _seed_project(tmp_path)
    stdin = json.dumps(
        {
            "ANSIBLE_MODULE_ARGS": {
                "device": "fireos-device",
                "repo_root": str(root),
                "connect": False,
                "_ansible_check_mode": True,
            }
        }
    )
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    captured = {}

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", lambda *a, **k: (0, "", ""))
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    with pytest.raises(SystemExit):
        mod.main()
    assert captured["changed"] is True
    assert captured["project_deployed"] is True
