#!/usr/bin/env python3
"""Run the Termux userland Ansible playbook for one device.

Usage: deploy_termux.py <oneui-device|fireos-device|stock-android-device|host>
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet" / "termux-userland.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR"]

sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as ac
import termux_ssh_bootstrap as boot
from ansible_context import (
    AnsibleConfigError,
    require_fresh_checkout,
    require_limit_hosts,
    resolve_ansible_context,
    resolved_env,
)


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
    parser.add_argument("host", help="Inventory host name (e.g. oneui-device)")
    args = parser.parse_args(argv)

    if not shutil.which("ansible-playbook"):
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        return 1
    if not shutil.which("secretspec"):
        print("ERROR: secretspec not found (brew install secretspec)", file=sys.stderr)
        return 1

    context = resolve_ansible_context(REPO_ROOT)
    require_limit_hosts(context, args.host)
    require_fresh_checkout(REPO_ROOT)

    target = ssh_target(args.host)
    print(f"Checking SSH to {target}...")
    if not verify_ssh(target):
        print(f"SSH to {target} failed — running ansible/playbooks/fleet/bootstrap.yml...")
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
            str(context.collections_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        cwd=REPO_ROOT,
    )

    rc = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "_secretspec",
            "env",
            "HOME=/var/db/stayturgid-secrets",
            "SECRETSPEC_PROVIDER=dotenv",
            "secretspec",
            "-f",
            "/var/db/stayturgid-secrets/secretspec.toml",
            "run",
            "--",
            "ansible-playbook",
            str(PLAYBOOK),
            "--limit",
            args.host,
        ],
        env=resolved_env(REPO_ROOT),
        cwd=REPO_ROOT,
    ).returncode
    if rc == 0:
        print(f"Done. Verify: ssh {target} '~/.stayturgid/bin/stayturgid_repair.py'")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
    except AnsibleConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
