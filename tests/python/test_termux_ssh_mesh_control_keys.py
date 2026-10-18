"""Guards for the SSH mesh host-key records on the control node (2026-10-18).

hostvars only hold the peers in the play, so a `--limit` deploy used to build an
empty known_hosts mesh. Each deploy now records its sshd host key on the control
node (tasks/ssh_keys.yml) and known_hosts_mesh.j2 reads those records for peers
outside the play.
"""

from __future__ import annotations

import json
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"
TEMPLATE = ROLE / "templates/known_hosts_mesh.j2"

KEY_A = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAA"
KEY_B = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBB"


def _render(inventory_hostname: str, hostvars: dict, keys_dir: Path) -> list[dict]:
    """Render the template with the few Ansible filters, tests and lookups it uses."""
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, extensions=["jinja2.ext.do"])
    env.filters["split"] = lambda s, sep=None: s.split(sep)
    env.filters["to_json"] = json.dumps
    env.filters["from_json"] = json.loads
    env.tests["file"] = lambda p: Path(p).is_file()

    def lookup(kind: str, path: str) -> str:
        assert kind == "ansible.builtin.file"
        return Path(path).read_text()

    env.globals["lookup"] = lookup
    out = env.from_string(TEMPLATE.read_text()).render(
        inventory_hostname=inventory_hostname,
        groups={"stayturgid": list(hostvars)},
        hostvars=hostvars,
        stayturgid_ssh_mesh_group="stayturgid",
        stayturgid_ssh_mesh_host_keys_dir=str(keys_dir),
    )
    return json.loads(out)


def _record(keys_dir: Path, host: str, key: str, aliases: list[str], port: int = 8022) -> None:
    rec = {"host": host, "key": key, "aliases": aliases, "port": port}
    (keys_dir / f"{host}.json").write_text(json.dumps(rec))


def test_peer_outside_the_play_comes_from_its_control_node_record(tmp_path: Path) -> None:
    _record(tmp_path, "p7a", KEY_B, ["p7a", "100.64.0.7"])
    hostvars = {
        "s24": {
            "inventory_hostname": "s24",
            "ansible_host": "100.64.0.24",
            "stayturgid_sshd_host_pubkey": KEY_A + " root@s24",
        },
        "p7a": {"inventory_hostname": "p7a", "ansible_host": "100.64.0.7"},
    }
    entries = _render("s24", hostvars, tmp_path)
    assert entries == [
        {"name": "[p7a]:8022", "key": "[p7a]:8022 " + KEY_B},
        {"name": "[100.64.0.7]:8022", "key": "[100.64.0.7]:8022 " + KEY_B},
    ]


def test_hostvars_key_wins_over_a_stale_record(tmp_path: Path) -> None:
    _record(tmp_path, "p7a", KEY_A, ["p7a"])
    hostvars = {
        "s24": {"inventory_hostname": "s24", "ansible_host": "100.64.0.24"},
        "p7a": {
            "inventory_hostname": "p7a",
            "ansible_host": "100.64.0.7",
            "stayturgid_ssh_known_host_aliases": ["p7a"],
            "stayturgid_sshd_host_pubkey": KEY_B + " comment",
        },
    }
    entries = _render("s24", hostvars, tmp_path)
    assert entries == [{"name": "[p7a]:8022", "key": "[p7a]:8022 " + KEY_B}]


def test_self_excluded_and_peer_without_key_or_record_skipped(tmp_path: Path) -> None:
    _record(tmp_path, "s24", KEY_A, ["s24"])
    hostvars = {
        "s24": {"inventory_hostname": "s24", "ansible_host": "100.64.0.24"},
        "hd8": {"inventory_hostname": "hd8", "ansible_host": "100.64.0.8"},
    }
    assert _render("s24", hostvars, tmp_path) == []


def _tasks() -> list[dict]:
    return yaml.safe_load((ROLE / "tasks/ssh_keys.yml").read_text())


def test_record_tasks_run_on_the_control_node_and_rewrite_identical_bytes() -> None:
    by_name = {t.get("name"): t for t in _tasks()}
    mkdir = by_name["Ensure SSH mesh host-key directory on control node"]
    write = by_name["Record this device's sshd host key on control node (SSH mesh)"]
    assert mkdir["delegate_to"] == write["delegate_to"] == "localhost"
    copy = write["ansible.builtin.copy"]
    # to_nice_json sorts keys, so an unchanged key gives identical content: ok, not changed.
    assert "to_nice_json" in copy["content"]
    assert copy["dest"].endswith("/{{ inventory_hostname }}.json")
    names = [t.get("name") for t in _tasks()]
    assert names.index(write["name"]) < names.index("Build SSH known_hosts mesh entries for this device")
