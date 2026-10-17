"""Device SSH must never reach the 1Password agent or a Touch ID-gated key.

Regression (t2e deploy, 2026-10-17): Ansible connects to `ansible_host`, a bare
IP, which matched no `Host <alias>` block, so ssh fell through to the global
`Host *` IdentityAgent (1Password) and offered the vps-primary key, raising a
Touch ID prompt. The generated config now matches the IP and pins one
passphrase-less key; every Python and Ansible ssh path adds the same pin.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import adb_cli  # noqa: E402
import stayturgid_device  # noqa: E402
import termux_ssh_bootstrap  # noqa: E402

PIN = ("IdentityAgent=none", "IdentitiesOnly=yes")
KEY = "/home/u/.ssh/termux_key"


def _render() -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(REPO / "ansible/roles/control_node/templates")))
    return env.get_template("ssh_config_stayturgid.j2").render(
        groups={"stayturgid": ["t2e", "hd8"]},
        hostvars={
            "t2e": {"ansible_host": "100.73.253.10", "device_lan_ip": "192.168.68.62"},
            "hd8": {"ansible_host": "100.124.55.39"},
        },
        stayturgid_ssh_identity_files=[KEY],
        stayturgid_firerpa_certificate_path="/k",
        stayturgid_live_lan_ips={},
    )


def _blocks(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    name = None
    for line in text.splitlines():
        if line.startswith("Host "):
            name = line
            out[name] = []
        elif name and line.strip() and not line.lstrip().startswith("#"):
            out[name].append(line.strip())
    return out


def test_device_blocks_match_the_bare_ansible_host_ip():
    blocks = _blocks(_render())
    assert "Host t2e 100.73.253.10" in blocks
    assert "Host hd8 100.124.55.39" in blocks


def test_every_device_block_is_pinned_and_never_uses_proxy_or_agent():
    text = _render()
    for name, lines in _blocks(text).items():
        assert "IdentityAgent none" in lines, name
        assert "IdentitiesOnly yes" in lines, name
        assert not any(re.match(r"Proxy(Jump|Command)\b", ln) for ln in lines), name
    # Only the explicit passphrase-less key is ever named for the SSH blocks.
    identity = {ln.split()[1] for ln in text.splitlines() if ln.strip().startswith("IdentityFile")}
    assert identity == {KEY, "/k"}


def test_identity_resolution_task_only_globs_termux_key():
    tasks = (REPO / "ansible/roles/control_node/tasks/agents.yml").read_text()
    assert "stayturgid_keys_dir ~ '/id_*'" not in tasks
    assert "stayturgid_ssh_keys_dir ~ '/id_*'" not in tasks
    assert "stayturgid_ssh_keys_dir ~ '/termux_key'" in tasks


def test_ansible_group_vars_pin_the_connection():
    data = yaml.safe_load((REPO / "ansible/inventory/group_vars/stayturgid.yml").read_text())
    args = data["ansible_ssh_common_args"]
    assert all(f"-o {opt}" in args for opt in PIN)


def _has_pin(opts: list[str]) -> bool:
    return all(opt in opts for opt in PIN) and all(opts[opts.index(opt) - 1] == "-o" for opt in PIN)


def test_python_ssh_options_are_pinned():
    for mod in (adb_cli, stayturgid_device, termux_ssh_bootstrap):
        assert _has_pin(mod.SSH_OPTS), mod.__name__
    deploy = (REPO / "control/bin/deploy_termux.py").read_text()
    assert '"IdentityAgent=none"' in deploy and '"IdentitiesOnly=yes"' in deploy
