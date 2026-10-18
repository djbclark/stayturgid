"""Termux's adb key survives a reinstall through the secret vault (2026-10-17).

A reinstall wipes ~/.android/adbkey; Termux generates a new key and adbd raises a new
"Allow USB debugging?" dialog (lost on a lock screen). adbd never revokes the old key,
so `capture` copies a phone's authorised key into the vault (TERMUX_ADBKEY_<HOST>) and
`restore` puts it back before Termux's first adb call. The key is never printed, put in
argv or written to disk on the control node.
"""

from __future__ import annotations

import base64
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import secretspec_exec as se
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control/lib"))
sys.path.insert(0, str(REPO / "ansible_collections/stayturgid/termux/plugins/module_utils"))

import termux_adbkey as vault
import termux_run_as as tr

# Built from parts so the file holds no literal private-key block for secret scanners.
_PEM = "-----" + "BEGIN PRIVATE KEY-----"
_PEM_END = "-----" + "END PRIVATE KEY-----"
PRIVATE = _PEM + "\nTUlJRXZnSUJBREFOQmdrcWhraUc5dzBCQVFFRkFBU0N=\nsecretsecretsecret\n" + _PEM_END + "\n"
PUBLIC = "QAAAAKeyBlobAAAA u0_a601@localhost\n"
SECRET_MARKER = "secretsecretsecret"


@pytest.fixture(autouse=True)
def brokered(monkeypatch):
    monkeypatch.setattr(se, "boundary_available", lambda: True)


# --- the seam: one secret per host, get/set/add only


def test_secret_name_is_the_prefix_plus_the_host():
    assert se.adbkey_secret_name("t2e") == "TERMUX_ADBKEY_T2E"
    assert se.adbkey_secret_name("s24") == "TERMUX_ADBKEY_S24"
    assert se.adbkey_secret_name("fire-hd-8") == "TERMUX_ADBKEY_FIRE_HD_8"
    with pytest.raises(ValueError):
        se.adbkey_secret_name("--")


def test_command_is_the_fixed_companion_call_with_a_reason():
    assert se.secretspec_adbkey_command("get", "TERMUX_ADBKEY_T2E") == [
        "sudo-secretspec",
        "get",
        "TERMUX_ADBKEY_T2E",
        "--reason",
        se.ADBKEY_REASON,
    ]
    assert se.secretspec_adbkey_command("set", "TERMUX_ADBKEY_T2E")[:3] == [
        "sudo-secretspec",
        "set",
        "TERMUX_ADBKEY_T2E",
    ]
    add = se.secretspec_adbkey_command("add", "TERMUX_ADBKEY_S24")
    assert "--optional" in add and "--description" in add and add[-2:] == ["--reason", se.ADBKEY_REASON]


@pytest.mark.parametrize(
    ("action", "name"),
    [
        ("export", "TERMUX_ADBKEY_T2E"),
        ("delete", "TERMUX_ADBKEY_T2E"),
        ("run", "TERMUX_ADBKEY_T2E"),
        ("get", "ANTHROPIC_API_KEY"),
        ("get", "TERMUX_ADBKEY_"),
        ("get", "termux_adbkey_t2e"),
        ("get", "TERMUX_ADBKEY_T2E; rm -rf"),
    ],
)
def test_seam_refuses_anything_but_get_set_add_of_an_adbkey_name(action, name):
    with pytest.raises(ValueError):
        se.secretspec_adbkey_command(action, name)


def test_no_boundary_means_no_adbkey_backup(monkeypatch):
    monkeypatch.setattr(se, "boundary_available", lambda: False)
    with pytest.raises(ValueError, match="adb key backup is unavailable"):
        se.secretspec_adbkey_command("get", "TERMUX_ADBKEY_T2E")


# --- the stored value


def test_pack_unpack_round_trip():
    value = vault.pack(PRIVATE, PUBLIC)
    assert "\n" not in value and value.startswith("adbkey1.")
    assert vault.unpack(value) == (PRIVATE, PUBLIC)
    assert vault.unpack(value + "\n") == (PRIVATE, PUBLIC)


@pytest.mark.parametrize("bad", ["", "adbkey2.QQ==.QQ==", "adbkey1.!!!.QQ==", "adbkey1.QQ==", "x.y.z.w"])
def test_unpack_rejects_what_is_not_a_packed_key(bad):
    with pytest.raises(ValueError):
        vault.unpack(bad)


def test_pack_refuses_something_that_is_not_an_adb_key():
    with pytest.raises(ValueError):
        vault.pack("just text", PUBLIC)
    with pytest.raises(ValueError):
        vault.pack(PRIVATE, "")


# --- vault calls: the value goes in on stdin only


class Vault:
    """subprocess.run fake for sudo-secretspec: declared names and stored values."""

    def __init__(self, declared=(), stored=None):
        self.declared = set(declared)
        self.stored = dict(stored or {})
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs.get("input")))
        action, name = cmd[1], cmd[2]
        if action == "get":
            if name in self.stored:
                return subprocess.CompletedProcess(cmd, 0, self.stored[name] + "\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "broker: %s is not resolved" % name)
        if action == "add":
            self.declared.add(name)
            return subprocess.CompletedProcess(cmd, 0, "declaration added", "")
        if action == "set":
            if name not in self.declared:
                return subprocess.CompletedProcess(cmd, 1, "", "Secret %s is not defined" % name)
            self.stored[name] = (kwargs.get("input") or "").strip()
            return subprocess.CompletedProcess(cmd, 0, "saved", "")
        raise AssertionError(cmd)


def test_vault_set_declares_an_unknown_name_then_sets_it(monkeypatch):
    fake = Vault()
    monkeypatch.setattr(vault.subprocess, "run", fake)
    vault.vault_set("TERMUX_ADBKEY_T2E", "VALUE")
    assert [c[0][1] for c in fake.calls] == ["set", "add", "set"]
    assert fake.stored["TERMUX_ADBKEY_T2E"] == "VALUE"


def test_vault_set_never_puts_the_value_in_argv(monkeypatch):
    fake = Vault(declared=["TERMUX_ADBKEY_T2E"])
    monkeypatch.setattr(vault.subprocess, "run", fake)
    value = vault.pack(PRIVATE, PUBLIC)
    vault.vault_set("TERMUX_ADBKEY_T2E", value)
    for cmd, stdin in fake.calls:
        assert SECRET_MARKER not in " ".join(cmd)
        assert value not in " ".join(cmd)
    assert fake.calls[0][1] == value


def test_vault_get_is_none_for_an_unset_name(monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", Vault())
    assert vault.vault_get("TERMUX_ADBKEY_T2E") is None


def test_vault_error_does_not_echo_the_value(monkeypatch):
    def broken(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "broker: audit denied")

    monkeypatch.setattr(vault.subprocess, "run", broken)
    with pytest.raises(vault.VaultError) as exc:
        vault.vault_set("TERMUX_ADBKEY_T2E", "SECRETVALUE")
    assert "SECRETVALUE" not in str(exc.value) and "audit denied" in str(exc.value)


# --- a fake phone: adbd's key store, Termux's files, run-as


class Phone:
    def __init__(self, *, private=PRIVATE, public=PUBLIC, authorized=True, run_as=True):
        self.files = {}
        if private is not None:
            self.files[tr.ADBKEY_PRIVATE] = private
            self.files[tr.ADBKEY_PUBLIC] = public
        self.authorized = authorized
        self.run_as = run_as
        self.writes = []
        self.argv = []

    def run(self, cmd):
        self.argv.append(cmd)
        joined = " ".join(cmd)
        if "run-as" in joined and joined.rstrip().endswith(" true"):
            return (0 if self.run_as else 1), "", ""
        if "dumpsys adb" in joined:
            return 0, ("user_keys:\n  %s\n" % tr.pubkey_blob(PUBLIC)) if self.authorized else "user_keys:\n", ""
        if "run-as" in joined:
            read = re.search(r"^cat (\S+)$", shlex.split(cmd[-1])[0], re.M)
            if read:
                path = read.group(1)
                if path in self.files:
                    return 0, self.files[path], ""
                return 1, "", "No such file"
        return 0, "", ""

    def run_with_input(self, cmd, data):
        self.argv.append(cmd)
        script = shlex.split(cmd[-1])[0]
        target = re.search(r"cat > (\S+)\.stg-new", script).group(1).strip("'")
        mode = re.search(r"chmod (\d+) \S+\.stg-new", script).group(1)
        self.writes.append((target, mode, data))
        self.files[target] = data
        return 0, "", ""


def test_capture_skips_a_key_adbd_has_not_authorised(monkeypatch):
    fake = Vault()
    monkeypatch.setattr(vault.subprocess, "run", fake)
    line = vault.capture("t2e", "S", run=Phone(authorized=False).run)
    assert "skipped" in line and "unauthorized" in line
    assert fake.calls == []


def test_capture_skips_a_phone_with_no_key_yet(monkeypatch):
    fake = Vault()
    monkeypatch.setattr(vault.subprocess, "run", fake)
    line = vault.capture("t2e", "S", run=Phone(private=None).run)
    assert "skipped" in line and "no-key" in line and fake.calls == []


def test_capture_stores_the_authorised_key_and_is_idempotent(monkeypatch):
    fake = Vault()
    monkeypatch.setattr(vault.subprocess, "run", fake)
    phone = Phone()
    assert vault.capture("t2e", "S", run=phone.run) == "capture: stored TERMUX_ADBKEY_T2E"
    assert vault.unpack(fake.stored["TERMUX_ADBKEY_T2E"]) == (PRIVATE, PUBLIC)
    assert vault.capture("t2e", "S", run=phone.run).startswith("capture: unchanged")


def test_capture_replaces_a_stale_stored_key_with_the_authorised_one(monkeypatch):
    stale = vault.pack(PRIVATE.replace(SECRET_MARKER, "oldoldoldoldold"), "QAAAAOldBlobZZZZ u0_a601@localhost\n")
    fake = Vault(declared=["TERMUX_ADBKEY_T2E"], stored={"TERMUX_ADBKEY_T2E": stale})
    monkeypatch.setattr(vault.subprocess, "run", fake)
    assert vault.capture("t2e", "S", run=Phone().run) == "capture: stored TERMUX_ADBKEY_T2E"
    assert vault.unpack(fake.stored["TERMUX_ADBKEY_T2E"])[1] == PUBLIC


def test_capture_status_lines_never_carry_the_key(monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", Vault())
    line = vault.capture("s24", "S", run=Phone().run)
    assert SECRET_MARKER not in line and "BEGIN" not in line


# --- restore


def test_restore_with_nothing_stored_does_nothing(monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", Vault())
    phone = Phone(private=None)
    assert vault.restore("t2e", "S", run=phone.run, run_with_input=phone.run_with_input).startswith(
        "restore: nothing stored"
    )
    assert phone.writes == []


def test_restore_writes_the_stored_key_when_the_phone_has_none(monkeypatch):
    fake = Vault(stored={"TERMUX_ADBKEY_T2E": vault.pack(PRIVATE, PUBLIC)})
    monkeypatch.setattr(vault.subprocess, "run", fake)
    phone = Phone(private=None)
    line = vault.restore("t2e", "S", run=phone.run, run_with_input=phone.run_with_input)
    assert line == "restore: restored t2e's own adb key from TERMUX_ADBKEY_T2E"
    assert phone.writes == [(tr.ADBKEY_PUBLIC, "0644", PUBLIC), (tr.ADBKEY_PRIVATE, "0600", PRIVATE)], (
        "public first, private last, private mode 0600"
    )


def test_restore_never_puts_the_private_key_in_argv(monkeypatch):
    fake = Vault(stored={"TERMUX_ADBKEY_T2E": vault.pack(PRIVATE, PUBLIC)})
    monkeypatch.setattr(vault.subprocess, "run", fake)
    phone = Phone(private=None)
    vault.restore("t2e", "S", run=phone.run, run_with_input=phone.run_with_input)
    assert not any(SECRET_MARKER in " ".join(cmd) for cmd in phone.argv)


def test_restore_leaves_a_phone_that_already_has_a_key_alone(monkeypatch):
    fake = Vault(stored={"TERMUX_ADBKEY_T2E": vault.pack(PRIVATE, PUBLIC)})
    monkeypatch.setattr(vault.subprocess, "run", fake)
    phone = Phone()
    line = vault.restore("t2e", "S", run=phone.run, run_with_input=phone.run_with_input)
    assert "already has an adb key" in line and phone.writes == []


def test_restore_waits_for_run_as(monkeypatch):
    fake = Vault(stored={"TERMUX_ADBKEY_T2E": vault.pack(PRIVATE, PUBLIC)})
    monkeypatch.setattr(vault.subprocess, "run", fake)
    phone = Phone(private=None, run_as=False)
    line = vault.restore("t2e", "S", run=phone.run, run_with_input=phone.run_with_input)
    assert "run-as" in line and phone.writes == []


def test_write_script_is_atomic_and_private():
    script = vault._write_script(tr.ADBKEY_PRIVATE, "0600")
    assert "umask 077" in script and "set -e" in script
    assert "cat > %s.stg-new" % tr.ADBKEY_PRIVATE in script
    assert "mv -f %s.stg-new %s" % (tr.ADBKEY_PRIVATE, tr.ADBKEY_PRIVATE) in script
    assert "/sdcard" not in script


# --- bootstrap-ssh restores before Termux's first adb call, and never blocks on it


def test_bootstrap_serial_restores_before_bootstrapping(monkeypatch):
    import termux_ssh_bootstrap as boot

    order = []
    monkeypatch.setattr(
        boot.termux_adbkey, "restore", lambda host, serial: order.append(("restore", host, serial)) or "restore: ok"
    )
    monkeypatch.setattr(boot.tr, "bootstrap_device", lambda *_a, **_k: order.append("bootstrap"))
    monkeypatch.setattr(boot, "discover_pubkey_paths", lambda *_a, **_k: [])
    monkeypatch.setattr(boot, "read_pubkey_lines", lambda *_a, **_k: ["ssh-ed25519 AAA k"])
    boot.bootstrap_serial("100.1.2.3:5555", forward=False, verify_alias="", host="t2e")
    assert order == [("restore", "t2e", "100.1.2.3:5555"), "bootstrap"]


def test_restore_trouble_only_prints_and_bootstrap_continues(monkeypatch, capsys):
    import termux_ssh_bootstrap as boot

    def broken(host, serial):
        raise ValueError("no sudo-secretspec boundary on this machine")

    monkeypatch.setattr(boot.termux_adbkey, "restore", broken)
    boot.restore_adbkey("S", "t2e")
    assert "adb key not restored on t2e" in capsys.readouterr().out
    boot.restore_adbkey("S", None)


# --- wiring in the playbooks and the role


def _tasks(path: Path) -> list[dict]:
    """Tasks of the play that bootstraps Termux (preflight.yml has a probe play before it)."""
    data = yaml.safe_load(path.read_text())
    if "hosts" not in data[0]:
        return data
    plays = [play for play in data if "bootstrap" in play["name"].lower()]
    return plays[0]["tasks"]


def test_both_bootstrap_playbooks_restore_before_the_bootstrap_module():
    for name, module_task in (
        ("bootstrap.yml", "Bootstrap Termux authorized_keys and sshd"),
        ("preflight.yml", "Bootstrap Termux authorized_keys and sshd over adb"),
    ):
        tasks = _tasks(REPO / "ansible/playbooks/fleet" / name)
        names = [t.get("name", "") for t in tasks]
        restore = tasks[names.index("Restore Termux's own adb key from the vault when the phone has none")]
        assert names.index(restore["name"]) < names.index(module_task)
        argv = restore["ansible.builtin.command"]["argv"]
        assert argv[1].endswith("/control/bin/termux_adbkey.py") and argv[2:4] == [
            "restore",
            "{{ inventory_hostname }}",
        ]
        assert restore["failed_when"] is False and restore["delegate_to"] == "localhost"
        assert (
            tasks[names.index(module_task)]["stayturgid.termux.termux_ssh_bootstrap"]["host"]
            == "{{ inventory_hostname }}"
        )


def test_deploy_captures_the_key_after_the_privileged_grant_without_failing_the_deploy():
    tasks = _tasks(REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml")
    names = [t.get("name", "") for t in tasks]
    capture = tasks[names.index("Back up Termux's adb key to the secret vault once it is authorised")]
    assert names.index(capture["name"]) > names.index("Grant Termux permissions via privileged shell")
    assert capture["failed_when"] is False and capture["delegate_to"] == "localhost"
    assert "capture" in capture["ansible.builtin.command"]["argv"]
    assert any("stayturgid_no_local_adb" in str(cond) for cond in capture["when"])


def test_the_cli_exits_3_when_the_vault_is_unavailable(monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("termux_adbkey_cli", REPO / "control/bin/termux_adbkey.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli.vault, "capture", lambda host, serial: (_ for _ in ()).throw(ValueError("no boundary")))
    assert cli.main(["capture", "t2e", "--device", "S"]) == 3
    assert "vault is unavailable for t2e" in capsys.readouterr().err
    monkeypatch.setattr(cli.vault, "capture", lambda host, serial: (_ for _ in ()).throw(RuntimeError("adb gone")))
    assert cli.main(["capture", "t2e", "--device", "S"]) == 1
    monkeypatch.setattr(cli.vault, "capture", lambda host, serial: "capture: stored TERMUX_ADBKEY_T2E")
    assert cli.main(["capture", "t2e", "--device", "S"]) == 0
    assert "stored TERMUX_ADBKEY_T2E" in capsys.readouterr().out


def test_b64_alphabet_has_no_dot_so_the_separator_is_safe():
    assert "." not in base64.b64encode(bytes(range(256))).decode()
