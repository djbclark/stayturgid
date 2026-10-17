"""Guards for the 2026-10-17 narrowing of the phones' authorized_keys.

Only the explicit `stayturgid_ssh_public_key_files` list is installed (default
termux_key.pub); the operator's personal keys the old `*.pub` glob installed are
removed by name, additively, so the fleet mesh and peer-help keys (which come from
the devices, not from this list) are never swept.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"


def _defaults() -> dict:
    return yaml.safe_load((ROLE / "defaults/main.yml").read_text())


def _tasks() -> list[dict]:
    return yaml.safe_load((ROLE / "tasks/ssh_keys.yml").read_text())


def _by_name(name: str) -> dict:
    return next(t for t in _tasks() if t.get("name") == name)


def test_allowed_public_keys_are_an_explicit_list_with_only_the_fleet_key():
    allowed = _defaults()["stayturgid_ssh_public_key_files"]
    assert allowed == ["{{ stayturgid_ssh_keys_dir }}/termux_key.pub"]


def test_personal_keys_are_retired_and_the_fleet_key_is_not():
    retired = set(_defaults()["stayturgid_ssh_retired_public_key_names"])
    assert {"id_ed25519_mit", "id_ed25519-djbclark-github", "id_rsa_gerrit_openafs"} <= retired
    # Everything else the old glob copied from the operator's ~/.ssh.
    assert {
        "1password_agent",
        "athena_tgt_push",
        "git_signing_key",
        "id_ed25519",
        "stayturgid_ca",
        "vps_primary_key",
    } <= retired
    defaults = _defaults()
    protected = {
        "termux_key",
        defaults["stayturgid_ssh_device_identity_key"],
        defaults["stayturgid_ssh_peerhelp_identity_key"],
        "id_ed25519_fleet",
    }
    assert not protected & retired
    allowed_names = {Path(p).stem for p in defaults["stayturgid_ssh_public_key_files"]}
    assert not allowed_names & retired


def test_no_glob_of_the_control_node_ssh_directory_remains():
    text = (ROLE / "tasks/ssh_keys.yml").read_text()
    assert "fileglob" not in text
    assert "/*.pub" not in text


def test_install_and_removal_are_additive_never_exclusive():
    install = _by_name("Install fleet SSH public keys from control node (ansible.posix.authorized_key)")
    removal = _by_name("Remove retired operator SSH public keys from authorized_keys")
    for task, state in ((install, "present"), (removal, "absent")):
        args = task["ansible.posix.authorized_key"]
        assert args["state"] == state
        # exclusive: true would drop the mesh keys on a `--limit` run, where the
        # other devices' published keys are not in hostvars.
        assert args["exclusive"] is False
    assert "_stayturgid_ssh_public_keys" in install["ansible.posix.authorized_key"]["key"]
    assert "_stayturgid_ssh_retired_public_keys" in removal["ansible.posix.authorized_key"]["key"]


def test_removal_runs_after_install_and_a_key_in_both_lists_is_rejected():
    names = [t.get("name") for t in _tasks()]
    assert names.index("Remove retired operator SSH public keys from authorized_keys") > names.index(
        "Install fleet SSH public keys from control node (ansible.posix.authorized_key)"
    )
    guard = _by_name("Reject a public key that is both installed and retired")
    assert "intersect" in guard["ansible.builtin.assert"]["that"][0]
    assert names.index(guard["name"]) < names.index(
        "Install fleet SSH public keys from control node (ansible.posix.authorized_key)"
    )


def test_mesh_keys_still_install_from_device_hostvars():
    mesh = _by_name("Install fleet device SSH public keys (mesh authorized_keys)")
    assert "_stayturgid_mesh_pubkeys" in mesh["ansible.posix.authorized_key"]["key"]
    assert mesh["ansible.posix.authorized_key"]["exclusive"] is False
