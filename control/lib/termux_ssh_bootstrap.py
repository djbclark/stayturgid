"""Bootstrap Termux SSH authorized_keys over adb (CLI wrapper).

Core logic lives in stayturgid.termux.plugins.module_utils.termux_run_as
(collection). This module adds Mac-side SSH verification after bootstrap.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_COLLECTION_UTILS = (
    REPO_ROOT / "ansible_collections" / "stayturgid" / "termux" / "plugins" / "module_utils"
)
if str(_COLLECTION_UTILS) not in sys.path:
    sys.path.insert(0, str(_COLLECTION_UTILS))

import termux_run_as as tr  # noqa: E402

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR"]

# Re-export discovery helpers for tests and callers.
default_keys_dir = tr.default_keys_dir
discover_pubkey_paths = tr.discover_pubkey_paths
read_pubkey_lines = tr.read_pubkey_lines
run_as_available = lambda serial: tr.run_as_available(_adb_run, serial)
termux_installed = lambda serial: tr.termux_installed(_adb_run, serial)


def _adb_run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).returncode, "", ""


def _run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout or "", result.stderr or ""


def forward_local_ssh(serial: str) -> None:
    subprocess.run(["adb", "-s", serial, "forward", "tcp:8022", "tcp:8022"], check=True)


def verify_ssh_local(private_key: Path) -> bool:
    result = subprocess.run(
        [
            "ssh",
            *SSH_OPTS,
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            str(private_key),
            "-p",
            "8022",
            "localhost",
            "echo",
            "termux_ssh_ok",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def verify_ssh_alias(host: str) -> bool:
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, "echo", "termux_ssh_ok"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def pick_private_key(keys_dir: Path | None = None) -> Path | None:
    root = Path(keys_dir) if keys_dir else Path(default_keys_dir())
    for candidate in (root / "termux_key", *sorted(root.glob("id_*"))):
        if candidate.is_file() and not str(candidate).endswith(".pub"):
            return candidate
    return None


def bootstrap_serial(
    serial: str,
    *,
    pubkey_paths: list[Path] | None = None,
    keys_dir: Path | None = None,
    install_openssh: bool = True,
    forward: bool = True,
    verify_alias: str = "",
) -> None:
    paths = pubkey_paths if pubkey_paths is not None else discover_pubkey_paths(keys_dir)
    lines = read_pubkey_lines([str(p) for p in paths])
    tr.bootstrap_device(
        _run_command,
        serial,
        lines,
        connect=True,
        install_openssh_pkg=install_openssh,
        start_sshd_service=True,
    )

    local_ok = False
    if forward:
        forward_local_ssh(serial)
        key = pick_private_key(keys_dir)
        if key:
            local_ok = verify_ssh_local(key)

    if verify_alias:
        if not verify_ssh_alias(verify_alias) and not local_ok:
            raise RuntimeError("SSH to %s failed after bootstrap" % verify_alias)
    elif forward and not local_ok:
        raise RuntimeError("SSH via adb forward tcp:8022 failed after bootstrap")


def bootstrap_alias(
    alias: str,
    resolve_adb,
    *,
    verify_alias: str | None = None,
    **kwargs,
) -> None:
    serial = resolve_adb(alias)
    bootstrap_serial(
        serial,
        verify_alias=verify_alias if verify_alias is not None else alias,
        **kwargs,
    )


def run_bootstrap_playbook(
    repo_root: Path,
    hosts: list[str],
    *,
    ansible_cfg: Path | None = None,
    collections_path: Path | None = None,
    requirements: Path | None = None,
) -> int:
    """Run ansible/playbooks/fleet/bootstrap.yml for inventory host(s)."""
    repo_root = Path(repo_root)
    cfg = ansible_cfg or repo_root / "ansible" / "ansible.cfg"
    playbook = repo_root / "ansible" / "playbooks" / "fleet" / "bootstrap.yml"
    req = requirements or repo_root / "ansible" / "requirements.yml"
    coll = collections_path or repo_root / ".ansible" / "collections"
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(cfg)
    subprocess.run(
        [
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            str(req),
            "-p",
            str(coll),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        cwd=repo_root,
    )
    cmd = ["ansible-playbook", str(playbook)]
    if hosts:
        cmd.extend(["--limit", ",".join(hosts)])
    return subprocess.run(cmd, env=env, cwd=repo_root).returncode
