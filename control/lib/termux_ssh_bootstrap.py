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
_COLLECTION_UTILS = REPO_ROOT / "ansible_collections" / "stayturgid" / "termux" / "plugins" / "module_utils"
if str(_COLLECTION_UTILS) not in sys.path:
    sys.path.insert(0, str(_COLLECTION_UTILS))

import termux_run_as as tr
from secretspec_exec import secretspec_run

# Hard cap on one SSH probe (2026-10-10: a wedged sshd hung bootstrap_ssh.py for 56 minutes).
SSH_PROBE_TIMEOUT_S = 15
ADB_TIMEOUT_S = 30
# `pkg install openssh` runs through _run_command and can take minutes.
BOOTSTRAP_CMD_TIMEOUT_S = 900

SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "ConnectTimeout=5",
    "-o",
    "ServerAliveInterval=2",
]

# Re-export discovery helpers for tests and callers.
default_keys_dir = tr.default_keys_dir
discover_pubkey_paths = tr.discover_pubkey_paths
read_pubkey_lines = tr.read_pubkey_lines


def run_as_available(serial):
    return tr.run_as_available(_adb_run, serial)


def termux_installed(serial):
    return tr.termux_installed(_adb_run, serial)


def _adb_run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=ADB_TIMEOUT_S)
    return result.returncode, result.stdout or "", result.stderr or ""


def _run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=BOOTSTRAP_CMD_TIMEOUT_S)
    return result.returncode, result.stdout or "", result.stderr or ""


def is_wedged(serial: str) -> bool:
    """True when sshd's listener has connections waiting that it never accepts.

    A healthy listener has Recv-Q 0; a wedged Termux sshd (seen on t2e 2026-10-10)
    sits at Recv-Q above its backlog, so every new connection times out.
    """
    rc, stdout, _ = _adb_run(["adb", "-s", serial, "shell", "ss", "-ltn"])
    if rc != 0:
        return False
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "LISTEN" and parts[3].endswith(":8022"):
            try:
                if int(parts[1]) > 0 and int(parts[1]) >= int(parts[2]):
                    return True
            except ValueError:
                continue
    return False


WEDGE_DIAGNOSTICS = [
    "dumpsys activity processes | grep -i -A10 com.termux",
    "ps -A -o PID,PPID,STAT,WCHAN,NAME | grep -E 'sshd|termux'",
    "ss -ltn | grep 8022",
]


def capture_wedge_diagnostics(serial: str) -> None:
    """Print what a force-stop is about to destroy (cached-app freezer hypothesis, 2026-10-10)."""
    for cmd in WEDGE_DIAGNOSTICS:
        try:
            _, out, _ = _adb_run(["adb", "-s", serial, "shell", cmd])
        except subprocess.TimeoutExpired:
            out = "(timed out)"
        print("wedge-diagnostic %s:\n%s" % (cmd, "\n".join(out.splitlines()[:30])))


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
        timeout=SSH_PROBE_TIMEOUT_S,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def verify_ssh_alias(host: str) -> bool:
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, "echo", "termux_ssh_ok"],
        capture_output=True,
        text=True,
        timeout=SSH_PROBE_TIMEOUT_S,
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

    def _do_bootstrap():
        tr.bootstrap_device(
            _run_command,
            serial,
            lines,
            connect=True,
            install_openssh_pkg=install_openssh,
            start_sshd_service=True,
        )

    _do_bootstrap()

    def _probe(key: Path | None) -> tuple[bool, bool, bool]:
        """(local_ok, alias_ok, timed_out); a probe that times out counts as failed."""
        local_ok = alias_ok = timed_out = False
        if forward and key:
            try:
                local_ok = verify_ssh_local(key)
            except subprocess.TimeoutExpired:
                timed_out = True
        if verify_alias:
            try:
                alias_ok = verify_ssh_alias(verify_alias)
            except subprocess.TimeoutExpired:
                timed_out = True
        return local_ok, alias_ok, timed_out

    key = None
    if forward:
        forward_local_ssh(serial)
        key = pick_private_key(keys_dir)
    local_ok, alias_ok, timed_out = _probe(key)

    if not local_ok and not alias_ok and (timed_out or is_wedged(serial)):
        # Wedged sshd: listening, never accepting. One force-stop of Termux, one
        # re-bootstrap (restarts sshd), one re-probe; never a loop.
        print("sshd on %s looks wedged: force-stopping Termux once" % serial)
        capture_wedge_diagnostics(serial)
        subprocess.run(
            ["adb", "-s", serial, "shell", "am", "force-stop", "com.termux"],
            check=False,
            timeout=30,
        )
        _do_bootstrap()
        local_ok, alias_ok, timed_out = _probe(key)
        if not local_ok and not alias_ok:
            raise RuntimeError("Termux sshd is wedged on %s and recovery failed" % serial)

    if verify_alias:
        if not alias_ok and not local_ok:
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
    cmd = secretspec_run("ansible-playbook", str(playbook))
    if hosts:
        cmd.extend(["--limit", ",".join(hosts)])
    return subprocess.run(cmd, env=env, cwd=repo_root).returncode
