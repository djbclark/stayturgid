"""Unit tests for termux_ssh_bootstrap module and termux_run_as helpers."""

import json

import pytest

from ansible_collections.stayturgid.termux.plugins.module_utils import termux_run_as as tr
from ansible_collections.stayturgid.termux.plugins.modules import termux_ssh_bootstrap as mod


def test_keys_need_install():
    assert tr.keys_need_install([], ["ssh-ed25519 AAA one"]) is True
    assert tr.keys_need_install(["ssh-ed25519 AAA one"], ["ssh-ed25519 AAA one"]) is False
    assert tr.keys_need_install(["ssh-ed25519 AAA one"], ["ssh-ed25519 BBB two"]) is True


def test_normalize_pubkey_lines():
    assert tr.normalize_pubkey_lines(["  ssh-ed25519 A ", "# skip", ""]) == ["ssh-ed25519 A"]


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
        if "run-as com.termux true" in joined:
            return (0, "", "")
        if "pm path com.termux" in joined:
            return (0, "package:com.termux\n", "")
        if "authorized_keys" in joined and "cat" in joined:
            return (1, "", "")
        if "pgrep -x sshd" in joined:
            return (1, "", "")
        if "test -x" in joined and "sshd" in joined:
            return (0, "", "")
        if "adb push" in joined:
            return (0, "", "")
        if "run-as com.termux" in joined and "bootstrap_ssh.sh" in joined:
            return (0, "", "")
        if "run-as com.termux" in joined and "sshd" in joined:
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


def test_termux_ssh_bootstrap_installs_keys(mocker, tmp_path):
    pub = tmp_path / "termux_key.pub"
    pub.write_text("ssh-ed25519 AAAAB3 test@host\n", encoding="utf-8")
    out = run_module(
        mocker,
        dict(
            device="RFCX219CHKA",
            connect=False,
            public_key_files=[str(pub)],
            install_openssh=False,
            start_sshd=False,
        ),
    )
    assert out["changed"] is True
    assert out["keys_changed"] is True
    assert out["public_key_count"] == 1


def test_termux_ssh_bootstrap_idempotent_when_present(mocker, tmp_path):
    pub = tmp_path / "k.pub"
    pub.write_text("ssh-ed25519 EXISTING key\n", encoding="utf-8")

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "run-as com.termux true" in joined:
            return (0, "", "")
        if "pm path" in joined:
            return (0, "package:com.termux\n", "")
        if "authorized_keys" in joined:
            return (0, "ssh-ed25519 EXISTING key\n", "")
        if "test -x" in joined and "sshd" in joined:
            return (0, "", "")
        if "pgrep -x sshd" in joined:
            return (0, "", "")
        return (0, "", "")

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    stdin = json.dumps(
        {
            "ANSIBLE_MODULE_ARGS": dict(
                device="dev",
                connect=False,
                public_key_files=[str(pub)],
                install_openssh=True,
                start_sshd=True,
            )
        }
    )
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
    assert captured["changed"] is False
