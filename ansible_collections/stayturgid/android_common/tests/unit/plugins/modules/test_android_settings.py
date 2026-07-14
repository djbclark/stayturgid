"""Unit tests for android_settings module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import android_settings as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if "pm path" in joined or "pm list packages" in joined:
            return (0, "package:com.tailscale.ipn\n", "")
        if "settings get" in joined:
            return (0, "null", "")
        if "settings put" in joined:
            return (0, "", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_android_settings_sets_vpn(mocker):
    out = run_module(
        mocker,
        dict(
            device="100.1.2.3:5555",
            connect=False,
            require_package="com.tailscale.ipn",
            settings=[
                dict(namespace="secure", key="always_on_vpn_app", value="com.tailscale.ipn"),
                dict(namespace="secure", key="always_on_vpn_lockdown", value="1"),
            ],
        ),
    )
    assert out["changed"] is True
    assert len(out["results"]) == 2


def test_android_settings_skips_missing_package(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            require_package="com.missing",
            settings=[
                dict(namespace="secure", key="always_on_vpn_app", value="com.tailscale.ipn"),
            ],
        ),
        cmd_results=[
            ("pm list packages", (0, "", "")),
        ],
    )
    assert out["skipped"] is True
    assert out["changed"] is False
