"""Unit tests for shared/mac/termux_ssh_bootstrap.py."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared", "mac"))
import termux_ssh_bootstrap as boot  # noqa: E402


def test_discover_pubkey_paths_explicit(tmp_path):
    pub = tmp_path / "termux_key.pub"
    pub.write_text("ssh-ed25519 AAA test\n", encoding="utf-8")
    found = boot.discover_pubkey_paths(explicit=[pub])
    assert found == [pub]


def test_discover_pubkey_paths_glob(tmp_path):
    (tmp_path / "a.pub").write_text("ssh-ed25519 A a\n", encoding="utf-8")
    (tmp_path / "b.pub").write_text("ssh-ed25519 B b\n", encoding="utf-8")
    (tmp_path / "termux_key").write_text("secret\n", encoding="utf-8")
    assert len(boot.discover_pubkey_paths(keys_dir=tmp_path)) == 2


def test_read_pubkey_lines_skips_comments(tmp_path):
    pub = tmp_path / "k.pub"
    pub.write_text("# comment\nssh-ed25519 AAA one\n\nssh-ed25519 BBB two\n", encoding="utf-8")
    assert boot.read_pubkey_lines([pub]) == ["ssh-ed25519 AAA one", "ssh-ed25519 BBB two"]


def test_install_keys_shell_merges_without_clobber():
    script = boot.install_keys_shell("/sdcard/stayturgid/tmp/bootstrap_keys.pub")
    assert "grep -qF" in script
    assert "authorized_keys" in script
    assert boot.TERMUX_HOME in script


def test_run_as_available(monkeypatch):
    def fake_adb(serial, *args):
        class R:
            returncode = 0 if args[:2] == ("shell", "run-as") else 1

        return R()

    monkeypatch.setattr(boot, "_adb", fake_adb)
    assert boot.run_as_available("serial") is True


def test_push_authorized_keys_stages_and_runs(monkeypatch, tmp_path):
    calls = {"push": [], "run_as": []}

    def fake_adb(serial, *args, **kwargs):
        if args[0] == "push":
            calls["push"].append(args[2])
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    def fake_run_as(serial, script, **kwargs):
        calls["run_as"].append(script)
        return 0, "", ""

    monkeypatch.setattr(boot, "_adb", fake_adb)
    monkeypatch.setattr(boot, "run_as_termux", fake_run_as)
    boot.push_authorized_keys("RFCX", ["ssh-ed25519 AAA stayturgid@test"])
    assert boot.STAGING_KEYS in calls["push"]
    assert boot.STAGING_SCRIPT in calls["push"]
    assert calls["run_as"]


def test_bootstrap_serial_requires_run_as(monkeypatch):
    monkeypatch.setattr(boot, "termux_installed", lambda _s: True)
    monkeypatch.setattr(boot, "run_as_available", lambda _s: False)
    try:
        boot.bootstrap_serial("s24", pubkey_paths=[Path("/fake.pub")])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "run-as" in str(exc)
