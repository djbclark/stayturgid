#!/usr/bin/env python3
"""Fleet deploy orchestration via ansible/playbooks/site.yml.

Canonical entry (from repo root)::

  ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/site.yml

This wrapper installs collections and **always** re-runs control_node/site.yml after
the fleet site playbook. Ansible ``--limit`` is device hosts only, so localhost
(control node) would otherwise be skipped — Mac agents/launchd must still refresh.

Usage:
  deploy_fleet.py [host ...]              # full site deploy
  deploy_fleet.py --scope fdroid s24      # F-Droid roles only
  deploy_fleet.py --scope play s24        # Play roles + Aurora UI
  CHECK=1 deploy_fleet.py s24             # ansible --check --diff (no post-UI / validate asserts)

Scopes map to ansible-playbook --tags on site.yml (see site.yml header).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSIBLE_CFG = REPO_ROOT / "ansible" / "ansible.cfg"
INVENTORY = REPO_ROOT / "ansible" / "inventory" / "hosts.yml"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
MAC_SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "control_node" / "site.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"
COLLECTIONS_PATH = REPO_ROOT / ".ansible" / "collections"


class Scope(str, Enum):
    FULL = "full"
    FDROID = "fdroid"
    PLAY = "play"
    APP_STORES = "app-stores"

    @property
    def ansible_tags(self) -> str | None:
        if self is Scope.FULL:
            return None
        if self is Scope.PLAY:
            return "play,post-ui"
        return self.value


def load_play_env(env: dict[str, str]) -> None:
    """Merge ~/.config/stayturgid/play.env into env (GPLAY_* for google-play)."""
    path = Path.home() / ".config" / "stayturgid" / "play.env"
    if not path.is_file():
        return
    try:
        text = path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in env:
            env[key] = val


def repo_env() -> dict[str, str]:
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ANSIBLE_CFG)
    load_play_env(env)
    return env


def check_mode(cli_check: bool) -> bool:
    return cli_check or os.environ.get("CHECK", "0") == "1"


def parse_inventory_hosts(data: dict, group: str = "stayturgid") -> list[str]:
    hosts = data[group]["hosts"]
    if isinstance(hosts, list):
        return list(hosts)
    return list(hosts.keys())


def inventory_hosts(group: str = "stayturgid") -> list[str]:
    result = subprocess.run(
        ["ansible-inventory", "-i", str(INVENTORY), "--list"],
        capture_output=True,
        text=True,
        check=True,
        env=repo_env(),
        cwd=REPO_ROOT,
    )
    return parse_inventory_hosts(json.loads(result.stdout), group)


def resolve_hosts(hosts: list[str]) -> list[str]:
    return hosts if hosts else inventory_hosts()


def require_ansible() -> None:
    if not shutil.which("ansible-playbook"):
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        sys.exit(1)


def install_collections() -> None:
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


def warn_prerequisites(scope: Scope) -> None:
    needs_fdroid = scope in (Scope.FULL, Scope.FDROID, Scope.APP_STORES)
    needs_apkeep = scope in (Scope.FULL, Scope.PLAY, Scope.APP_STORES)
    if needs_fdroid and not shutil.which("fdroidcl"):
        msg = "fdroidcl not found (brew install fdroidcl)"
        if scope is Scope.FDROID:
            print("ERROR: " + msg, file=sys.stderr)
        else:
            print("WARNING: " + msg + " — F-Droid repo sync will fail", file=sys.stderr)
    if needs_apkeep and not shutil.which("apkeep"):
        print(
            "WARNING: apkeep not found (brew install apkeep) — Aurora auto-install will fail",
            file=sys.stderr,
        )
    env = repo_env()
    if needs_apkeep and not (env.get("GPLAY_AAS_TOKEN") or env.get("GPLAY_AUTH_TOKEN")):
        print(
            "WARNING: no GPLAY_AAS_TOKEN — google-play ensure_apps will fail "
            "(run control/tools/play/obtain_play_aas.py → ~/.config/stayturgid/play.env)",
            file=sys.stderr,
        )


def run_playbook(
    playbook: Path,
    *,
    limit: list[str] | None = None,
    check: bool,
    tags: str | None,
    skip_tags: str | None = None,
    extra_vars: list[str] | None = None,
    verbose: int = 0,
) -> int:
    cmd = ["ansible-playbook", str(playbook)]
    if limit:
        cmd.extend(["--limit", ",".join(limit)])
    if check:
        cmd.extend(["--check", "--diff"])
    if tags:
        cmd.extend(["--tags", tags])
    if skip_tags:
        cmd.extend(["--skip-tags", skip_tags])
    if extra_vars:
        cmd.extend(extra_vars)
    if verbose:
        cmd.append("-" + "v" * min(verbose, 4))
    return subprocess.run(cmd, env=repo_env(), cwd=REPO_ROOT).returncode


def deploy_mac(*, check: bool, tags: str = "mac", verbose: int = 0) -> int:
    """Mac localhost playbooks are not affected by device --limit."""
    return run_playbook(
        MAC_SITE_PLAYBOOK,
        check=check,
        tags=tags,
        verbose=verbose,
    )


def deploy(scope: Scope, hosts: list[str], *, check: bool, verbose: int = 0) -> int:
    require_ansible()
    warn_prerequisites(scope)
    install_collections()

    targets = resolve_hosts(hosts)
    # preflight.yml owns SSH bootstrap; skip the redundant bootstrap.yml pass in
    # both normal deploys and dry runs.
    skip_bootstrap = "bootstrap"
    rc = run_playbook(
        SITE_PLAYBOOK,
        limit=targets,
        check=check,
        tags=scope.ansible_tags,
        skip_tags=skip_bootstrap,
        verbose=verbose,
    )
    # A dry-run must not require local administrator credentials. The control-node
    # agent role includes privileged /etc configuration, and its normal deploy is
    # independent of the device host check below.
    if check:
        return rc
    # Always refresh Mac control node on real deploys: deploy_fleet always passes a
    # device --limit, so site.yml's control_node import never selects localhost.
    mac_rc = deploy_mac(check=False, verbose=verbose)
    return rc if rc != 0 else mac_rc


def print_footer(rc: int, scope: Scope) -> None:
    print()
    if rc != 0:
        print(f"Fleet deploy finished with errors (exit {rc}). Failed hosts are listed above.", file=sys.stderr)
    elif scope is Scope.FDROID:
        print("Fdroid scope finished (app stores parked — set stayturgid_app_stores_enabled: true to activate).")
    elif scope is Scope.PLAY:
        print("Play scope finished (app stores parked — set stayturgid_app_stores_enabled: true to activate).")
    else:
        print("Fleet deploy complete.")
    print("Verify: just verify   (or just verify-heal / bash tests/run.sh device --heal)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the stayturgid fleet stack.")
    parser.add_argument("hosts", nargs="*", help="Inventory host(s); default = whole stayturgid group")
    parser.add_argument(
        "--scope",
        choices=[s.value for s in Scope],
        default=Scope.FULL.value,
        help="Deploy scope (default: full site.yml)",
    )
    parser.add_argument("--check", action="store_true", help="Ansible dry run (--check --diff); also honors CHECK=1")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Ansible verbosity (-v, -vv, -vvv, -vvvv); also honors VERBOSE=N env",
    )
    args = parser.parse_args(argv)

    verbose = args.verbose or int(os.environ.get("VERBOSE", "0"))
    scope = Scope(args.scope)
    if scope is Scope.FDROID and not shutil.which("fdroidcl"):
        print("ERROR: fdroidcl not found (brew install fdroidcl)", file=sys.stderr)
        return 1

    rc = deploy(scope, args.hosts, check=check_mode(args.check), verbose=verbose)
    print_footer(rc, scope)
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
