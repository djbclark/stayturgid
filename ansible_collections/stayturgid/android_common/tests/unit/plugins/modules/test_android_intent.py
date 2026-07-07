"""Unit tests for android_intent module."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import android_intent as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}
    commands = []

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        commands.append(joined)
        for needle, result in (cmd_results or []):
            if needle in joined:
                return result
        if "am start" in joined:
            return (0, "Starting: Intent", "")
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
    return captured, commands


def test_android_intent_explicit(mocker):
    out, cmds = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            data="fdroidrepos://apt.izzysoft.de/fdroid/repo",
            component="com.machiav3lli.fdroid/.NeoActivity",
        ),
    )
    assert out["changed"] is True
    assert out["used_component"] is True
    assert any("NeoActivity" in c for c in cmds)


def test_android_intent_fallback(mocker):
    out, cmds = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            data="market://details?id=com.example",
            component="com.aurora.store/.MainActivity",
        ),
        cmd_results=[
            ("MainActivity", (1, "Error: Activity class does not exist", "")),
        ],
    )
    assert out["used_component"] is False
    assert len([c for c in cmds if "am start" in c]) >= 2
