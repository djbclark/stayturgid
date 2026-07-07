"""Unit tests for termux_sshd module."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import termux_sshd as mod  # noqa: E402


def test_merge_keys_exclusive():
    merged = mod.merge_keys(
        ["ssh-ed25519 AAAA old@host"],
        ["ssh-ed25519 BBBB new@host"],
        exclusive=True,
    )
    assert merged == ["ssh-ed25519 BBBB new@host"]


def test_merge_keys_additive():
    merged = mod.merge_keys(
        ["ssh-ed25519 AAAA old@host"],
        ["ssh-ed25519 BBBB new@host"],
        exclusive=False,
    )
    assert len(merged) == 2


def test_apply_config_replaces_existing():
    text = "Port 8022\n#PerSourcePenalties yes\n"
    out = mod.apply_config(text, {"PerSourcePenalties": "no"})
    assert "PerSourcePenalties no" in out
    assert "PerSourcePenalties yes" not in out


def run_module(mocker, args, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    prefix = tmp_path / "termux"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "etc" / "ssh").mkdir(parents=True)
    sshd_config = prefix / "etc" / "ssh" / "sshd_config"
    sshd_config.write_text("Port 8022\n")
    sshd_bin = prefix / "bin" / "sshd"
    sshd_bin.write_text("#!/bin/sh\nexit 0\n")
    sshd_bin.chmod(0o755)
    bash_bin = prefix / "bin" / "bash"
    bash_bin.write_text("#!/bin/sh\nexit 0\n")
    bash_bin.chmod(0o755)

    args = dict(args)
    args.setdefault("termux_prefix", str(prefix))

    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "sshd -t" in joined:
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

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(1)),
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_termux_sshd_updates_config(mocker, tmp_path, monkeypatch):
    out = run_module(
        mocker,
        dict(
            keys=[],
            config={"PerSourcePenalties": "no"},
            restart_on_change=False,
        ),
        tmp_path,
        monkeypatch,
    )
    assert out["config_changed"] is True
    assert out["changed"] is True
