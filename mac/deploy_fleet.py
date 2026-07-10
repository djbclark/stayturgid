#!/usr/bin/env python3
"""Fleet deploy orchestration via ansible/playbooks/site.yml.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSIBLE_CFG = REPO_ROOT / "ansible" / "ansible.cfg"
INVENTORY = REPO_ROOT / "ansible" / "inventory" / "hosts.yml"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"
COLLECTIONS_PATH = REPO_ROOT / ".ansible" / "collections"

sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as ac  # noqa: E402
import termux_ssh_bootstrap as boot  # noqa: E402


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
    return list(data[group]["hosts"].keys())


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


def build_playbook_argv(
    *,
    limit: list[str],
    check: bool,
    tags: str | None,
    skip_tags: str | None = None,
) -> list[str]:
    cmd = ["ansible-playbook", str(SITE_PLAYBOOK)]
    if limit:
        cmd.extend(["--limit", ",".join(limit)])
    if check:
        cmd.extend(["--check", "--diff"])
    if tags:
        cmd.extend(["--tags", tags])
    if skip_tags:
        cmd.extend(["--skip-tags", skip_tags])
    return cmd


def require_ansible() -> None:
    if not shutil.which("ansible-playbook"):
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        sys.exit(1)


def ssh_target(host: str) -> str:
    return ac.resolve_ssh(host) or host


def hosts_without_ssh(hosts: list[str]) -> list[str]:
    return [h for h in hosts if not ac.ssh_ok(ssh_target(h))]


def ensure_ssh_bootstrap(hosts: list[str]) -> int:
    need = hosts_without_ssh(hosts)
    if not need:
        return 0
    print(f"SSH preflight failed for {', '.join(need)} — running bootstrap playbook...")
    rc = boot.run_bootstrap_playbook(REPO_ROOT, need)
    if rc != 0:
        return rc
    still = hosts_without_ssh(need)
    if still:
        print(
            f"ERROR: SSH still unavailable after bootstrap: {', '.join(still)}",
            file=sys.stderr,
        )
        return 1
    return 0


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
        print(
            "WARNING: fdroidcl not found (brew install fdroidcl) — F-Droid repo sync will fail",
            file=sys.stderr,
        )
    if needs_apkeep and not shutil.which("apkeep"):
        print(
            "WARNING: apkeep not found (brew install apkeep) — Aurora auto-install will fail",
            file=sys.stderr,
        )
    env = repo_env()
    if needs_apkeep and not (env.get("GPLAY_AAS_TOKEN") or env.get("GPLAY_AUTH_TOKEN")):
        print(
            "WARNING: no GPLAY_AAS_TOKEN — google-play ensure_apps will fail "
            "(run play/mac/obtain_play_aas.py → ~/.config/stayturgid/play.env)",
            file=sys.stderr,
        )


def run_playbook(*, limit: list[str], check: bool, tags: str | None, skip_tags: str | None = None) -> int:
    cmd = build_playbook_argv(limit=limit, check=check, tags=tags, skip_tags=skip_tags)
    return subprocess.run(cmd, env=repo_env(), cwd=REPO_ROOT).returncode


def deploy(scope: Scope, hosts: list[str], *, check: bool) -> int:
    require_ansible()
    warn_prerequisites(scope)
    install_collections()

    targets = resolve_hosts(hosts)
    skip_bootstrap = None
    if not check:
        need = hosts_without_ssh(targets)
        if need:
            rc = ensure_ssh_bootstrap(need)
            if rc != 0:
                return rc
        else:
            skip_bootstrap = "bootstrap"
    return run_playbook(
        limit=targets,
        check=check,
        tags=scope.ansible_tags,
        skip_tags=skip_bootstrap,
    )


def print_footer(rc: int, scope: Scope) -> None:
    print()
    if rc != 0:
        print(f"Fleet deploy finished with errors (exit {rc}). Failed hosts are listed above.", file=sys.stderr)
    elif scope is Scope.FDROID:
        print(
            "Fdroid scope finished (app stores parked — set "
            "stayturgid_app_stores_enabled: true to activate)."
        )
    elif scope is Scope.PLAY:
        print(
            "Play scope finished (app stores parked — set "
            "stayturgid_app_stores_enabled: true to activate)."
        )
    else:
        print("Fleet deploy complete.")
    print("Verify: make verify   (or bash tests/run.sh device --heal)")


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
    args = parser.parse_args(argv)

    scope = Scope(args.scope)
    if scope is Scope.FDROID and not shutil.which("fdroidcl"):
        print("ERROR: fdroidcl not found (brew install fdroidcl)", file=sys.stderr)
        return 1

    rc = deploy(scope, args.hosts, check=check_mode(args.check))
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
