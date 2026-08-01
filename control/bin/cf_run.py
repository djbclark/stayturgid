#!/usr/bin/env python3
"""Run the CFEngine repair policy over SSH for selected fleet targets."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib.fleet_targets import resolve_hosts

CF_AGENT = "/data/data/com.termux/files/usr/bin/cf-agent"
CF_POLICY = "~/.stayturgid/cfengine/stayturgid.cf"


def cf_command(host: str) -> list[str]:
    """Build the SSH command for one inventory-derived SSH alias."""

    return [
        "ssh",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "BatchMode=yes",
        host,
        f"export PATH=/data/data/com.termux/files/usr/bin:$PATH; {CF_AGENT} -Kf {CF_POLICY} -D android,linux",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hosts", nargs="*", help="inventory SSH aliases; explicit hosts override offline status")
    parser.add_argument("--dry-run", action="store_true", help="print selected targets without SSH")
    args = parser.parse_args(argv)

    targets = resolve_hosts(args.hosts, repo_root=REPO_ROOT, command_name="cf-run")
    if not targets:
        print("cf-run: no eligible targets.", file=sys.stderr)
        return 0
    if args.dry_run:
        print("cf-run targets: " + ", ".join(targets))
        return 0

    failed = 0
    for host in targets:
        print(f"=== {host} ===")
        result = subprocess.run(cf_command(host), text=True)
        if result.returncode:
            failed += 1
        print("---")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
