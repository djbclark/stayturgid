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
            device="EXAMPLE-SERIAL-ONEUI",
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

    calls = []

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        calls.append(joined)
        if "run-as com.termux true" in joined:
            return (0, "", "")
        if "pm path" in joined:
            return (0, "package:com.termux\n", "")
        if "authorized_keys" in joined:
            return (0, "ssh-ed25519 EXISTING key\n", "")
        if "test -x" in joined and "sshd" in joined:
            return (0, "", "")
        # Liveness is sshd's SELinux domain, not a bare pgrep: sshd started via
        # run-as lands in runas_app, which has no /sdcard mount (#306). Report
        # one already running in untrusted_app — the "already present" case this
        # test is named for. `ps -A -Z` puts the context first, the name last.
        if "ps -A -Z" in joined:
            return (0, "u:r:untrusted_app:s0:c123,c256,c512,c768 u0_a601 4321 1 sshd\n", "")
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
    # Idempotent means it left the running sshd alone: no restart typed into
    # the Termux app's terminal, and no pkill of the existing one.
    assert not [c for c in calls if "input text sshd" in c]
    assert not [c for c in calls if "pkill -x sshd" in c]


def fake_adb(inversion_after_put):
    """run_command stand-in tracking the inversion setting; sshd shows up once typed."""
    state = {"inv": "0", "typed": False}
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "settings put secure " + tr.INVERSION_KEY in joined:
            state["inv"] = cmd[-1] if cmd[-1] != "1" else inversion_after_put
        elif "settings get secure " + tr.INVERSION_KEY in joined:
            return (0, state["inv"] + "\n", "")
        elif "input text sshd" in joined:
            state["typed"] = state["inv"] == "1"
        elif "ps -A -Z" in joined and state["typed"]:
            return (0, "u:r:untrusted_app:s0 u0_a601 4321 1 sshd\n", "")
        return (0, "", "")

    return run, state, calls


def test_start_sshd_from_app_types_only_while_inverted(mocker):
    mocker.patch.object(tr.time, "sleep")
    run, state, calls = fake_adb(inversion_after_put="1")
    assert tr.start_sshd_from_app(run, "dev") is True
    assert state["typed"] is True
    assert state["inv"] == "0"  # restored to what it was
    typed = next(i for i, c in enumerate(calls) if "input text sshd" in c)
    assert any("settings put secure %s 1" % tr.INVERSION_KEY in c for c in calls[:typed])


def test_start_sshd_from_app_refuses_without_inversion(mocker):
    mocker.patch.object(tr.time, "sleep")
    run, state, calls = fake_adb(inversion_after_put="0")
    with pytest.raises(RuntimeError, match="display inversion"):
        tr.start_sshd_from_app(run, "dev")
    assert not [c for c in calls if " input " in c]
