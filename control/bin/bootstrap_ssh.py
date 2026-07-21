#!/usr/bin/env python3
"""Bootstrap Termux SSH keys over adb (replaces manual ssh-copy-id).

Installs every control-node ``*.pub`` into Termux ``~/.ssh/authorized_keys``,
starts ``sshd``, and verifies SSH (USB forward and/or inventory SSH alias).

Requires a debuggable Termux build with working ``run-as com.termux`` (fleet
default on fireos-device; see docs/hacking.md). Keys are read from the Mac only — never
committed to git.

Usage:
  ./control/bin/bootstrap_ssh.py oneui-device
  ./control/bin/bootstrap_ssh.py --keys-dir ~/.ssh oneui-device stock-android-device
  ./control/bin/bootstrap_ssh.py --pubkey ~/.ssh/termux_key.pub fireos-device
  ./control/bin/bootstrap_ssh.py --ansible oneui-device stock-android-device   # inventory hosts via bootstrap.yml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as ac
import termux_ssh_bootstrap as boot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Termux SSH via adb.")
    parser.add_argument("hosts", nargs="+", help="Fleet alias or adb serial")
    parser.add_argument(
        "--keys-dir",
        type=Path,
        default=None,
        help="Directory of *.pub keys (default: ~/.ssh or STAYTURGID_SSH_KEYS_DIR)",
    )
    parser.add_argument(
        "--pubkey",
        action="append",
        dest="pubkeys",
        type=Path,
        help="Explicit public key file (repeatable; overrides auto-discovery)",
    )
    parser.add_argument(
        "--no-install-openssh",
        action="store_true",
        help="Skip pkg install when sshd binary is missing",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="Skip adb forward tcp:8022 and localhost SSH verify",
    )
    parser.add_argument(
        "--no-tailscale-verify",
        action="store_true",
        help="Skip SSH verify via inventory alias (still verifies USB forward unless --no-forward)",
    )
    parser.add_argument(
        "--ansible",
        action="store_true",
        help="Use ansible/playbooks/fleet/bootstrap.yml (inventory host names only)",
    )
    args = parser.parse_args(argv)

    pubkey_paths = args.pubkeys if args.pubkeys else None
    failed = 0

    if args.ansible:
        print("=== SSH bootstrap (ansible): %s ===" % ", ".join(args.hosts))
        rc = boot.run_bootstrap_playbook(REPO_ROOT, list(args.hosts))
        if rc != 0:
            return rc
        for host in args.hosts:
            alias = ac.resolve_ssh(host) or host
            if args.no_tailscale_verify or boot.verify_ssh_alias(alias):
                print("OK: %s — SSH bootstrapped (run deploy_fleet.py for full mesh sync)" % host)
            else:
                print("FAIL: %s — bootstrap playbook ran but SSH to %s failed" % (host, alias), file=sys.stderr)
                failed += 1
        return 1 if failed else 0

    for host in args.hosts:
        print("=== SSH bootstrap: %s ===" % host)
        try:
            boot.bootstrap_alias(
                host,
                ac.resolve_target,
                pubkey_paths=pubkey_paths,
                keys_dir=args.keys_dir,
                install_openssh=not args.no_install_openssh,
                forward=not args.no_forward,
                verify_alias="" if args.no_tailscale_verify else ac.resolve_ssh(host) or host,
            )
            print("OK: %s — SSH bootstrapped (run deploy_fleet.py for full mesh sync)" % host)
        except (RuntimeError, ValueError) as exc:
            print("FAIL: %s — %s" % (host, exc), file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
