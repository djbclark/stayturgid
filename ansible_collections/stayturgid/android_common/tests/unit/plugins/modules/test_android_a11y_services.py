"""Unit tests for android_a11y_services module."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import android_a11y_services as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in (cmd_results or []):
            if needle in joined:
                return result
        if "settings get" in joined:
            return (0, "", "")
        if "settings put" in joined:
            return (0, "", "")
        return (0, "", "")

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


def test_a11y_backup_writes_file(mocker, tmp_path):
    profiles = tmp_path / "shared"
    profiles.mkdir()
    (profiles / "a11y_profiles.json").write_text('{"devices": {"s24": {"services": []}}}')
    out = run_module(
        mocker,
        dict(
            device="dev",
            alias="s24",
            repo_root=str(tmp_path),
            state="backup",
            connect=False,
        ),
        cmd_results=[
            ("settings get", (0, "com.foo/.Bar", "")),
        ],
    )
    assert out["changed"] is True
    backup = profiles / "a11y_backups" / "s24.txt"
    assert backup.is_file()
    assert "com.foo/.Bar" in backup.read_text()


def test_a11y_present_no_change_when_match(mocker, tmp_path):
    profiles = tmp_path / "shared"
    profiles.mkdir()
    (profiles / "a11y_profiles.json").write_text('{"devices": {"s24": {"services": []}}}')
    autojs = mod.a11y.AUTOJS6_A11Y
    out = run_module(
        mocker,
        dict(
            device="dev",
            alias="s24",
            repo_root=str(tmp_path),
            state="present",
            connect=False,
        ),
        cmd_results=[
            ("settings get", (0, autojs, "")),
        ],
    )
    assert out["changed"] is False
