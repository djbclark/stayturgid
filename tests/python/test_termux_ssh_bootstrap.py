"""Unit tests for termux_run_as helpers and CLI wrapper."""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
_COLLECTION_UTILS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ansible_collections",
    "stayturgid",
    "termux",
    "plugins",
    "module_utils",
)
sys.path.insert(0, _COLLECTION_UTILS)

import pytest
import termux_run_as as tr
import termux_ssh_bootstrap as boot


def test_discover_pubkey_paths_explicit(tmp_path):
    pub = tmp_path / "termux_key.pub"
    pub.write_text("ssh-ed25519 AAA test\n", encoding="utf-8")
    found = tr.discover_pubkey_paths(explicit=[str(pub)])
    assert found == [str(pub)]


def test_discover_pubkey_paths_glob(tmp_path):
    (tmp_path / "a.pub").write_text("ssh-ed25519 A a\n", encoding="utf-8")
    (tmp_path / "b.pub").write_text("ssh-ed25519 B b\n", encoding="utf-8")
    (tmp_path / "termux_key").write_text("secret\n", encoding="utf-8")
    assert len(tr.discover_pubkey_paths(keys_dir=str(tmp_path))) == 2


def test_read_pubkey_lines_skips_comments(tmp_path):
    pub = tmp_path / "k.pub"
    pub.write_text("# comment\nssh-ed25519 AAA one\n\nssh-ed25519 BBB two\n", encoding="utf-8")
    assert tr.read_pubkey_lines([str(pub)]) == ["ssh-ed25519 AAA one", "ssh-ed25519 BBB two"]


def test_install_keys_shell_merges_without_clobber():
    script = tr.install_keys_shell(["ssh-ed25519 AAA a@b"])
    assert "grep -qF" in script
    assert "authorized_keys" in script
    assert tr.TERMUX_HOME in script
    assert "ssh-ed25519 AAA a@b" in script
    assert "/sdcard" not in script


def test_run_as_available(monkeypatch):
    def fake_run(cmd):
        joined = " ".join(cmd)
        rc = 0 if "run-as com.termux true" in joined else 1
        return rc, "", ""

    monkeypatch.setattr(tr, "adb_cmd", lambda run_command, device, *args: fake_run(["adb"] + list(args)))
    assert tr.run_as_available(lambda c: fake_run(c), "serial") is True


def test_push_authorized_keys_runs_inline_script(monkeypatch):
    scripts = []
    monkeypatch.setattr(tr, "run_as_termux", lambda rc, dev, script: scripts.append(script) or (0, "", ""))
    monkeypatch.setattr(tr, "read_authorized_keys", lambda *_a, **_k: ([], ""))
    assert tr.push_authorized_keys(lambda c: (0, "", ""), "RFCX", ["ssh-ed25519 AAA stayturgid@test"]) is True
    assert len(scripts) == 1 and "ssh-ed25519 AAA stayturgid@test" in scripts[0]


def test_run_as_termux_quotes_script_as_single_word():
    seen = []
    tr.run_as_termux(lambda c: seen.append(c) or (0, "", ""), "S", "a\nb 'c'")
    cmd = seen[0]
    assert cmd[-3:-1] == [tr.TERMUX_BASH, "-c"]
    assert cmd[-1] == "'a\nb '\"'\"'c'\"'\"''"


def test_ensure_sshd_leaves_app_context_sshd_alone(monkeypatch):
    monkeypatch.setattr(tr, "sshd_domain", lambda *_a: "u:r:untrusted_app_27:s0:c1")
    assert tr.ensure_sshd(lambda c: (0, "", ""), "S") is False


def test_ensure_sshd_replaces_runas_sshd(monkeypatch):
    domains = iter(["u:r:runas_app:s0:c1", "u:r:untrusted_app_27:s0:c1"])
    monkeypatch.setattr(tr, "sshd_domain", lambda *_a: next(domains))
    monkeypatch.setattr(tr, "start_sshd_from_app", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "run_as_termux", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(tr.time, "sleep", lambda _s: None)
    assert tr.ensure_sshd(lambda c: (0, "", ""), "S") is True


def test_bootstrap_device_requires_run_as(monkeypatch):
    monkeypatch.setattr(tr, "termux_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "run_as_available", lambda *_a, **_k: False)
    try:
        tr.bootstrap_device(lambda c: (0, "", ""), "oneui-device", ["ssh-ed25519 A"])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "run-as" in str(exc)


def _fake_runner(run_log, *, ssh_fails_until=0, ss_line="LISTEN 129 128 [::]:8022 *:*"):
    """subprocess.run fake: the first `ssh_fails_until` ssh probes hang, adb ss shows a wedge."""
    ssh_calls = []

    def fake_run(cmd, **kwargs):
        run_log.append(cmd)
        if cmd[0] == "ssh":
            ssh_calls.append(cmd)
            if len(ssh_calls) <= ssh_fails_until:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
            return subprocess.CompletedProcess(cmd, 0, "termux_ssh_ok", "")
        if "ss" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ss_line, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return fake_run


def _patch_bootstrap(monkeypatch, fake_run):
    monkeypatch.setattr(boot.subprocess, "run", fake_run)
    monkeypatch.setattr(boot, "_run_command", lambda c: (0, "", ""))
    monkeypatch.setattr(boot, "pick_private_key", lambda d: "key")
    monkeypatch.setattr(boot.tr, "bootstrap_device", lambda *a, **k: None)


def test_ssh_probe_has_hard_timeout(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, "termux_ssh_ok", "")

    monkeypatch.setattr(boot.subprocess, "run", fake_run)
    assert boot.verify_ssh_local("key")
    assert seen["timeout"] == boot.SSH_PROBE_TIMEOUT_S
    assert boot.verify_ssh_alias("host")
    assert seen["timeout"] == boot.SSH_PROBE_TIMEOUT_S


def test_is_wedged_reads_accept_queue(monkeypatch):
    wedged = "LISTEN 129 128 [::]:8022 *:*"
    healthy = "LISTEN 0 128 [::]:8022 *:*"
    other_port = "LISTEN 129 128 [::]:18022 *:*"
    for line, want in ((wedged, True), (healthy, False), (other_port, False)):
        monkeypatch.setattr(boot, "_adb_run", lambda cmd, line=line: (0, line, ""))
        assert boot.is_wedged("serial") is want


def test_wedge_recovery_is_one_shot(monkeypatch):
    run_log = []
    _patch_bootstrap(monkeypatch, _fake_runner(run_log, ssh_fails_until=1))
    monkeypatch.setattr(boot, "_adb_run", lambda cmd: (0, "LISTEN 129 128 [::]:8022 *:*", ""))

    boot.bootstrap_serial("serial", forward=True, verify_alias="", install_openssh=False)

    assert len([c for c in run_log if "force-stop" in c]) == 1
    assert len([c for c in run_log if c[0] == "ssh"]) == 2


def test_wedge_second_failure_is_reported_not_looped(monkeypatch):
    run_log = []
    _patch_bootstrap(monkeypatch, _fake_runner(run_log, ssh_fails_until=99))
    monkeypatch.setattr(boot, "_adb_run", lambda cmd: (0, "LISTEN 129 128 [::]:8022 *:*", ""))

    with pytest.raises(RuntimeError, match="wedged"):
        boot.bootstrap_serial("serial", forward=True, verify_alias="", install_openssh=False)

    assert len([c for c in run_log if "force-stop" in c]) == 1
    assert len([c for c in run_log if c[0] == "ssh"]) == 2


def test_healthy_ssh_never_force_stops(monkeypatch):
    run_log = []
    _patch_bootstrap(monkeypatch, _fake_runner(run_log))

    boot.bootstrap_serial("serial", forward=True, verify_alias="", install_openssh=False)

    assert not [c for c in run_log if "force-stop" in c]


def test_adb_run_returns_real_output(monkeypatch):
    """is_wedged reads `ss` output through _adb_run; stdout must not be discarded."""
    monkeypatch.setattr(
        boot.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "LISTEN 129 128 [::]:8022 *:*", ""),
    )
    assert boot.is_wedged("serial") is True


def test_wedge_diagnostics_are_printed_before_force_stop(monkeypatch, capsys):
    run_log = []
    _patch_bootstrap(monkeypatch, _fake_runner(run_log, ssh_fails_until=1))

    boot.bootstrap_serial("serial", forward=True, verify_alias="", install_openssh=False)

    assert "wedge-diagnostic" in capsys.readouterr().out
