#!/usr/bin/env python3
"""Run the Termux userland Ansible playbook for one device.

Usage: deploy_termux.py <s24|hd8|p7a|host>
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSIBLE_CFG = REPO_ROOT / "ansible" / "ansible.cfg"
PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "termux-userland.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"
COLLECTIONS_PATH = REPO_ROOT / ".ansible" / "collections"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR"]

sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as ac  # noqa: E402
import termux_ssh_bootstrap as boot  # noqa: E402


def ssh_target(host: str) -> str:
    return ac.resolve_ssh(host) or host


def verify_ssh(target: str) -> bool:
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [target, "echo termux_ssh_ok"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy Termux userland via Ansible.")
    parser.add_argument("host", help="Inventory host name (e.g. s24)")
    args = parser.parse_args(argv)

    if not shutil.which("ansible-playbook"):
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        return 1

    target = ssh_target(args.host)
    print(f"Checking SSH to {target}...")
    if not verify_ssh(target):
        print(f"SSH to {target} failed — running ansible/playbooks/bootstrap.yml...")
        rc = boot.run_bootstrap_playbook(REPO_ROOT, [args.host])
        if rc != 0:
            print(f"ERROR: bootstrap playbook failed (exit {rc})", file=sys.stderr)
            return rc
        if not verify_ssh(target):
            print(
                f"ERROR: cannot SSH to {target} after bootstrap — "
                "check Tailscale or use: ssh -p 8022 localhost (with adb forward)",
                file=sys.stderr,
            )
            return 1

    subprocess.run(
        [
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            str(REQUIREMENTS),
            "-p",
            str(COLLECTIONS_PATH),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        cwd=REPO_ROOT,
    )

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ANSIBLE_CFG)
    rc = subprocess.run(
        ["ansible-playbook", str(PLAYBOOK), "--limit", args.host],
        env=env,
        cwd=REPO_ROOT,
    ).returncode
    if rc == 0:
        print(f"Done. Verify: ssh {target} '~/stayturgid-repair.sh'")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
