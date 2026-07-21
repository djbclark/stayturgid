"""Unit tests for android_ui module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import android_ui as mod


def run_module(mocker, args):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(1)),
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_android_ui_skips_check_mode(mocker, tmp_path):
    script = tmp_path / "obtainium" / "mac"
    script.mkdir(parents=True)
    (script / "import_catalog.py").write_text("# stub\n")
    out = run_module(
        mocker,
        dict(
            host="oneui-device",
            task="import_obtainium_catalog",
            repo_root=str(tmp_path),
            _ansible_check_mode=True,
        ),
    )
    assert out["skipped"] is True
    assert out["changed"] is False


def test_android_ui_runs_script(mocker, tmp_path):
    script = tmp_path / "control" / "tools" / "autojs6"
    script.mkdir(parents=True)
    (script / "enable_autojs6_shizuku.py").write_text("# stub\n")
    mocker.patch.object(mod.subprocess, "run", return_value=mocker.Mock(returncode=0))
    out = run_module(
        mocker,
        dict(
            host="stock-android-device",
            task="enable_autojs6_drawer",
            repo_root=str(tmp_path),
        ),
    )
    assert out["changed"] is True
    assert out["rc"] == 0
