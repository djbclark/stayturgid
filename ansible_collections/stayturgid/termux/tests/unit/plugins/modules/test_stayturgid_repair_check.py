"""Unit tests for stayturgid_repair_check module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import stayturgid_repair_check as mod


def test_find_status_line_picks_last():
    out = "log noise\nSTATUS port=open shizuku=up sshd=up a11y=up shell=yes\n"
    assert mod.find_status_line(out).startswith("STATUS port=open")


def test_parse_status_with_a11y():
    parsed = mod.parse_status_line("STATUS port=open shizuku=up sshd=up a11y=up shell=yes")
    assert parsed["port"] == "open"
    assert parsed["a11y"] == "up"


def test_parse_status_without_a11y():
    parsed = mod.parse_status_line("STATUS port=skip shizuku=skip sshd=up shell=no")
    assert parsed["port"] == "skip"
    assert parsed.get("a11y") is None


def test_is_healthy_open_and_skip():
    assert mod.is_healthy({"port": "open"}) is True
    assert mod.is_healthy({"port": "skip"}) is True
    assert mod.is_healthy({"port": "CLOSED_NO_SHELL"}) is False


def run_module(
    mocker,
    args,
    tmp_path,
    monkeypatch,
    script_body="#!/bin/bash\necho STATUS port=open shizuku=up sshd=up a11y=up shell=yes\nexit 0\n",
):
    monkeypatch.setenv("HOME", str(tmp_path))
    prefix = tmp_path / "termux"
    (prefix / "bin").mkdir(parents=True)
    bash = prefix / "bin" / "bash"
    bash.write_text('#!/bin/sh\nexec /bin/sh "$@"\n')
    bash.chmod(0o755)

    script = tmp_path / "repair.sh"
    script.write_text(script_body)
    script.chmod(0o755)

    args = dict(args)
    args.setdefault("repair_script", str(script))
    args.setdefault("termux_prefix", str(prefix))

    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(str(c) for c in cmd)
        if "repair" in joined:
            rc = 1 if "exit 1" in script_body else 0
            return (
                rc,
                "STATUS port=open shizuku=up sshd=up a11y=up shell=yes\n",
                "",
            )
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


def test_repair_check_healthy(mocker, tmp_path, monkeypatch):
    out = run_module(mocker, {}, tmp_path, monkeypatch)
    assert out["healthy"] is True
    assert out["port"] == "open"
    assert out["changed"] is False


def test_repair_check_check_mode(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": {"_ansible_check_mode": True}})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    captured = {}

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    with pytest.raises(SystemExit):
        mod.main()
    assert captured["skipped"] is True
