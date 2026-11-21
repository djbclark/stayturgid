"""termux_ssh_bootstrap must send the phone's own $HOME to adb, never the Mac's.

s24, 2026-11-21: ``module.run_command`` expanded ``$HOME`` in the Termux script on the control node, so the
phone ran ``mkdir -p /Users/<operator>/.ssh`` (read-only file system) and read the wrong authorized_keys.
"""

import json
import os

import pytest

from ansible_collections.stayturgid.android_common.plugins.module_utils.plain_run import plain_run_command
from ansible_collections.stayturgid.termux.plugins.module_utils import termux_run_as as tr
from ansible_collections.stayturgid.termux.plugins.modules import termux_ssh_bootstrap as mod

MAC_HOME = "/Users/mac-operator"
SSH_DIR = "$HOME/.ssh"


def real_module(mocker):
    from ansible.module_utils import basic

    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": {}}).encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    return basic.AnsibleModule(argument_spec={})


def fake_adb(tmp_path, monkeypatch):
    """An `adb` that prints its last argument (the Termux script) and exits 0."""
    fake = tmp_path / "bin" / "adb"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nfor last; do :; done\nprintf '%s' \"$last\"\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", "%s:%s" % (fake.parent, os.environ["PATH"]))


def test_run_as_script_reaches_adb_with_the_phones_home_not_the_macs(mocker, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", MAC_HOME)
    fake_adb(tmp_path, monkeypatch)
    module = plain_run_command(real_module(mocker))
    for script in (tr.install_keys_shell(["ssh-ed25519 AAAA k"]), tr.read_authorized_keys_shell()):
        rc, out, _err = tr.run_as_termux(module.run_command, "dev", script)
        assert rc == 0
        assert '"%s' % SSH_DIR in out
        assert "$PATH" in out
        assert MAC_HOME not in out


def test_unwrapped_run_command_would_have_sent_the_macs_home(mocker, monkeypatch, tmp_path):
    # The same chain without the wrapper shows the bug the test above guards against.
    monkeypatch.setenv("HOME", MAC_HOME)
    fake_adb(tmp_path, monkeypatch)
    module = real_module(mocker)
    _rc, out, _err = tr.run_as_termux(module.run_command, "dev", tr.read_authorized_keys_shell())
    assert "%s/.ssh/authorized_keys" % MAC_HOME in out


def test_termux_ssh_bootstrap_never_asks_ansible_to_expand_device_commands(mocker, tmp_path):
    pub = tmp_path / "k.pub"
    pub.write_text("ssh-ed25519 AAAAB3 test@host\n", encoding="utf-8")
    kwargs_seen = []

    def recording_run_command(self, cmd, *a, **kw):
        kwargs_seen.append(kw)
        joined = " ".join(cmd)
        if "pm path" in joined:
            return (0, "package:com.termux\n", "")
        if "authorized_keys" in joined and "cat" in joined:
            return (1, "", "")
        return (0, "", "")

    args = dict(device="dev", connect=False, public_key_files=[str(pub)], install_openssh=False, start_sshd=False)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", recording_run_command)
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": args}).encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(0)),
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(1)),
    )
    with pytest.raises(SystemExit):
        mod.main()
    assert kwargs_seen
    assert all(kw.get("expand_user_and_vars") is False for kw in kwargs_seen)
