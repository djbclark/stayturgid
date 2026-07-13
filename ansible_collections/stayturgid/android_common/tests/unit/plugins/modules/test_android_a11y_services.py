"""Unit tests for android_a11y_services module (detection-only)."""
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


def test_a11y_report_shows_autojs6_present(mocker):
    autojs = mod.a11y.AUTOJS6_A11Y
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=[
            ("settings get", (0, autojs, "")),
        ],
    )
    assert out["autojs6_present"] is True
    assert autojs in out["services"]


def test_a11y_report_shows_autojs6_missing(mocker):
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=[
            ("settings get", (0, "com.foo/.Bar", "")),
        ],
    )
    assert out["autojs6_present"] is False
    assert "com.foo/.Bar" in out["services"]


def test_a11y_report_empty_list(mocker):
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=[
            ("settings get", (0, "null", "")),
        ],
    )
    assert out["autojs6_present"] is False
    assert out["services_count"] == 0
