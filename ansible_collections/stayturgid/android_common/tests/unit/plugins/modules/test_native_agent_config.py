"""Unit tests for native_agent_config module."""

import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[4] / "plugins" / "modules" / "native_agent_config.py"
SPEC = importlib.util.spec_from_file_location("native_agent_config", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_desired_config_is_complete_and_stable():
    assert mod.desired_config(["100.0.0.3:5555"], "moe.shizuku.privileged.api") == {
        "shizuku_pkg": "moe.shizuku.privileged.api",
        "targets": ["100.0.0.3:5555"],
    }


@pytest.mark.parametrize("text", ["", "[]", "not json", '{"targets":'])
def test_parse_config_rejects_invalid_or_non_mapping(text):
    assert mod.parse_config(text) is None


def test_parse_config_ignores_formatting():
    value = {"targets": [], "shizuku_pkg": "moe.shizuku.privileged.api"}
    assert mod.parse_config(json.dumps(value, indent=4)) == value


def test_external_config_path_is_package_scoped():
    assert (
        mod.external_config_path("org.stayturgid.agent") == "/sdcard/Android/data/org.stayturgid.agent/files/peer.json"
    )


def run_module(mocker, args, command_fn):
    """Drive main with mocked Ansible module I/O."""
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        return command_fn(cmd)

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    def fake_fail(self, **kw):
        captured.update(kw, failed=True)
        raise SystemExit(1)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_not_installed_guard_fails_closed(mocker):
    result = run_module(
        mocker,
        {"device": "dev", "targets": [], "connect": False},
        lambda _cmd: (0, "", ""),
    )

    assert result["failed"] is True
    assert "is not installed" in result["msg"]


def test_check_mode_reports_change_without_writing(mocker):
    commands = []

    def command(cmd):
        commands.append(cmd)
        joined = " ".join(cmd)
        if "pm list packages" in joined:
            return (0, "package:org.stayturgid.agent\n", "")
        if "cat " in joined:
            return (1, "", "missing")
        return (0, "", "")

    result = run_module(
        mocker,
        {
            "device": "dev",
            "targets": ["100.0.0.3:5555"],
            "connect": False,
            "_ansible_check_mode": True,
        },
        command,
    )

    assert result == {
        "changed": True,
        "failed": False,
        "path": "/sdcard/Android/data/org.stayturgid.agent/files/peer.json",
    }
    assert not any(" push " in f" {' '.join(cmd)} " for cmd in commands)


def test_staging_failure_fails_closed(mocker):
    def command(cmd):
        joined = " ".join(cmd)
        if "pm list packages" in joined:
            return (0, "package:org.stayturgid.agent\n", "")
        if "cat " in joined:
            return (1, "", "missing")
        if " push " in f" {joined} ":
            return (1, "", "push denied")
        return (0, "", "")

    result = run_module(
        mocker,
        {"device": "dev", "targets": ["100.0.0.3:5555"], "connect": False},
        command,
    )

    assert result["failed"] is True
    assert "staging failed" in result["msg"]


def test_post_write_verification_mismatch_fails_closed(mocker):
    cat_calls = 0

    def command(cmd):
        nonlocal cat_calls
        joined = " ".join(cmd)
        if "pm list packages" in joined:
            return (0, "package:org.stayturgid.agent\n", "")
        if "cat " in joined:
            cat_calls += 1
            return (0, "{}\n", "")
        return (0, "", "")

    result = run_module(
        mocker,
        {"device": "dev", "targets": ["100.0.0.3:5555"], "connect": False},
        command,
    )

    assert cat_calls == 2
    assert result["failed"] is True
    assert "verification failed" in result["msg"]
