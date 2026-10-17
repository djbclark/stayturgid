"""Guards for the 2026-10-17 deploy-termux speed and hardening changes.

1. Phones get an explicit private-key list in one transfer; the operator's
   personal keys are never copied and are removed from devices by name.
2. The storage grant a fresh Termux needs runs from the control node's adb
   before SSH, and the boot-loop handler tolerates a fresh install.
3. otelcol ships as the archive and is unpacked on the device only when the
   installed version differs from the pin.
4. SSH ControlPersist is 10 minutes in every ansible.cfg source.
"""

from __future__ import annotations

import configparser
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"


def _tasks(name: str) -> list[dict]:
    return yaml.safe_load((ROLE / "tasks" / name).read_text())


def _defaults() -> dict:
    return yaml.safe_load((ROLE / "defaults/main.yml").read_text())


def _walk(tasks: list[dict]):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            yield from _walk(task.get(key, []))


def _by_name(tasks: list[dict], name: str) -> dict:
    return next(t for t in _walk(tasks) if t.get("name") == name)


def test_private_key_allowlist_is_explicit_and_excludes_personal_keys():
    defaults = _defaults()
    assert defaults["stayturgid_ssh_private_key_names"] == ["termux_key"]
    retired = set(defaults["stayturgid_ssh_retired_private_key_names"])
    assert {"id_ed25519_mit", "id_ed25519-djbclark-github", "id_rsa_gerrit_openafs"} <= retired
    if_copied = set(defaults["stayturgid_ssh_retired_if_copied_private_key_names"])
    assert "id_ed25519" in if_copied
    # Never remove or distribute the device's own identities or the allowed keys.
    protected = {
        defaults["stayturgid_ssh_device_identity_key"],
        defaults["stayturgid_ssh_peerhelp_identity_key"],
        *defaults["stayturgid_ssh_private_key_names"],
    }
    assert not protected & (retired | if_copied)


def test_ssh_keys_task_file_no_longer_globs_private_keys():
    text = (ROLE / "tasks/ssh_keys.yml").read_text()
    assert "'/id_*'" not in text
    assert "_stayturgid_ssh_private_key_paths" not in text


def test_private_keys_move_in_one_synchronize_and_verify_in_one_task():
    tasks = _tasks("ssh_keys.yml")
    install = _by_name(tasks, "Install fleet SSH private keys on device")
    assert "ansible.posix.synchronize" in install
    assert "loop" not in install
    sync_args = install["ansible.posix.synchronize"]
    assert "--exclude=*" in sync_args["rsync_opts"]
    # ~/.ssh's mtime moves whenever authorized_keys is rewritten earlier in the run.
    assert "--omit-dir-times" in sync_args["rsync_opts"]
    # recursive: false makes rsync skip the source directory and copy nothing.
    assert sync_args.get("recursive", True) is True
    verify = _by_name(tasks, "Verify fleet SSH private keys on device (present, mode 0600)")
    assert "loop" not in verify
    assert not [t for t in tasks if t.get("name", "").startswith("Fail if SSH private key missing")]


def test_retired_keys_are_removed_after_the_install_task():
    tasks = _tasks("ssh_keys.yml")
    names = [t.get("name") for t in tasks]
    assert names.index("Remove private keys no longer distributed to the device") > names.index(
        "Install fleet SSH private keys on device"
    )
    removal = _by_name(tasks, "Remove private keys no longer distributed to the device")
    assert "stayturgid_ssh_retired_private_key_names" in removal["ansible.builtin.shell"]
    assert "removed:" in removal["changed_when"]


def test_otelcol_installs_from_archive_only_on_version_mismatch():
    tasks = _tasks("otelcol.yml")
    names = [t.get("name") for t in tasks]
    assert "Install cached otelcol-contrib binary" not in names
    block = _by_name(tasks, "Install otelcol-contrib from the cached archive")
    assert "_otelcol_needs_install" in "".join(block["when"])
    unpack = _by_name(block["block"], "Unpack the cached otelcol-contrib archive on the device")
    assert unpack["ansible.builtin.unarchive"]["src"] == "{{ stayturgid_otelcol_cached_archive }}"
    # The 380 MB unpacked binary is no longer copied over SSH.
    copies = [t for t in _walk(tasks) if "ansible.builtin.copy" in t]
    assert not [t for t in copies if "cached_binary" in str(t["ansible.builtin.copy"].get("src", ""))]
    move = _by_name(block["block"], "Move the unpacked otelcol-contrib binary into place")
    assert move["notify"] == "restart otelcol"
    cleanup = block["always"][0]["ansible.builtin.file"]
    assert cleanup["state"] == "absent"
    assert cleanup["path"] == "{{ stayturgid_otelcol_unpack_dir }}"
    # Scratch space is under the Termux home, never /sdcard.
    assert _defaults()["stayturgid_otelcol_unpack_dir"].startswith("{{ termux_home }}/")
    probe_idx = names.index("Probe installed otelcol-contrib version")
    assert probe_idx < names.index("Install otelcol-contrib from the cached archive")


def test_boot_loop_handler_skips_when_start_adb_is_not_deployed_yet():
    handlers = yaml.safe_load((ROLE / "handlers/main.yml").read_text())
    script = next(h for h in handlers if h["name"] == "restart boot loop")["ansible.builtin.shell"]
    guard = script.split("pidf=")[0]
    assert '-x "$HOME/.termux/boot/start-adb.sh"' in guard
    assert "exit 0" in guard


def test_storage_grant_runs_first_from_the_control_node_before_any_ssh():
    plays = yaml.safe_load((REPO / "ansible/playbooks/fleet/termux-userland.yml").read_text())
    first = plays[0]
    assert first["gather_facts"] is False
    grant = _by_name(first["tasks"], "Grant Termux shared-storage permissions when missing")
    assert grant["delegate_to"] == "localhost"
    args = grant["stayturgid.android_common.android_appops"]
    assert args["appops"] == [{"package": "com.termux", "op": "MANAGE_EXTERNAL_STORAGE", "mode": "allow"}]
    assert {p["permission"] for p in args["permissions"]} == {
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
    }
    # A failure is reported, never fatal: the later /sdcard task names the cause.
    assert any("rescue" in t for t in first["tasks"])
    assert plays[1]["roles"] == [{"role": "stayturgid.termux.termux_userland"}]


def _parse_cfg(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    return parser


def test_ansible_cfg_sources_keep_ten_minute_control_persist():
    for path in (
        REPO / "ansible/ansible.cfg",
        REPO / "control/site_contract/templates/ansible.cfg.j2",
        Path.home() / "ops/site-djbclark/ansible.cfg",
    ):
        if not path.exists():  # the live site overlay only exists on the operator's Mac
            continue
        section = _parse_cfg(path.read_text())["ssh_connection"]
        # Ansible's default ssh_args, with ControlPersist 60s -> 10m and nothing dropped.
        assert section["ssh_args"] == "-C -o ControlMaster=auto -o ControlPersist=10m", path
        assert section["pipelining"] == "True", path
