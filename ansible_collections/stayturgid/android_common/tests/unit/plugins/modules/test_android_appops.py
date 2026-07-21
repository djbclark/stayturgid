"""Unit tests for android_appops module helpers."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_shell
import android_appops as mod


def test_parse_appops_mode():
    assert adb_shell.parse_appops_mode("WRITE_SETTINGS: allow") == "allow"
    assert adb_shell.parse_appops_mode("SYSTEM_ALERT_WINDOW: ignore") == "ignore"
    assert adb_shell.parse_appops_mode("") == ""


def test_package_installed_from_pm_list():
    def run(_cmd):
        return (0, "package:com.termux\n", "")

    assert adb_shell.package_installed(run, "dev", "com.termux") is True
    assert adb_shell.package_installed(run, "dev", "com.missing") is False


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
        if "pm list packages" in joined:
            return (0, "package:com.termux\npackage:com.termux.api\n", "")
        if "cmd appops get" in joined:
            return (0, "default", "")
        if "cmd appops set" in joined:
            return (0, "", "")
        if "pm grant" in joined:
            return (0, "granted", "")
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


def test_android_appops_sets_missing_ops(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            connect=False,
            appops=[
                dict(package="com.termux.api", op="WRITE_SETTINGS", mode="allow"),
            ],
            permissions=[],
        ),
    )
    assert out["changed"] is True
    assert out["results"][0]["status"] == "set"


def test_android_appops_already_allowed(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            appops=[
                dict(package="com.termux", op="SYSTEM_ALERT_WINDOW", mode="allow"),
            ],
            permissions=[],
        ),
        cmd_results=[
            ("cmd appops get com.termux SYSTEM_ALERT_WINDOW", (0, "allow", "")),
        ],
    )
    assert out["changed"] is False
    assert out["results"][0]["status"] == "already"


def test_android_appops_already_granted(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            appops=[],
            permissions=[
                dict(
                    package="com.termux.api",
                    permission="android.permission.POST_NOTIFICATIONS",
                ),
            ],
        ),
        cmd_results=[
            (
                "dumpsys package com.termux.api",
                (
                    0,
                    "android.permission.POST_NOTIFICATIONS: granted=true, flags=[]",
                    "",
                ),
            ),
        ],
    )
    assert out["changed"] is False
    assert out["results"][0]["status"] == "already"
