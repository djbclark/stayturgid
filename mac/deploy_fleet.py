#!/usr/bin/env python3
"""Fleet deploy orchestration (Ansible + Obtainium import + app-store follow-ups).

Usage:
  deploy_fleet.py [host ...]              # full fleet deploy
  deploy_fleet.py --scope fdroid s24      # F-Droid roles only
  deploy_fleet.py --scope play s24        # Play roles + Aurora UI setup
  CHECK=1 deploy_fleet.py s24             # ansible --check --diff (no post-steps)

Scopes:
  full       — playbook, Obtainium import, app-stores re-run, Aurora UI (default)
  fdroid     — fleet.yml --tags fdroid
  play       — fleet.yml --tags play + Aurora UI (live only)
  app-stores — fleet.yml --tags app-stores (live only)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSIBLE_CFG = REPO_ROOT / "ansible" / "ansible.cfg"
INVENTORY = REPO_ROOT / "ansible" / "inventory" / "hosts.yml"
FLEET_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"
COLLECTIONS_PATH = REPO_ROOT / ".ansible" / "collections"
IMPORT_CATALOG = REPO_ROOT / "obtainium" / "mac" / "import_catalog.py"
CONFIGURE_AURORA = REPO_ROOT / "play" / "mac" / "configure_aurora.py"
ENABLE_AUTOJS6_SHIZUKU = REPO_ROOT / "autojs6" / "mac" / "enable_autojs6_shizuku.py"
HARDEN_FLEET_APPS = REPO_ROOT / "mac" / "harden_fleet_apps.py"


class Scope(str, Enum):
    FULL = "full"
    FDROID = "fdroid"
    PLAY = "play"
    APP_STORES = "app-stores"

    @property
    def ansible_tags(self) -> str | None:
        if self is Scope.FULL:
            return None
        return self.value


def repo_env() -> dict[str, str]:
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ANSIBLE_CFG)
    return env


def check_mode(cli_check: bool) -> bool:
    return cli_check or os.environ.get("CHECK", "0") == "1"


def parse_inventory_hosts(data: dict, group: str = "stayturgid") -> list[str]:
    """Extract host names from ansible-inventory --list JSON."""
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
) -> list[str]:
    cmd = ["ansible-playbook", str(FLEET_PLAYBOOK)]
    if limit:
        cmd.extend(["--limit", ",".join(limit)])
    if check:
        cmd.extend(["--check", "--diff"])
    if tags:
        cmd.extend(["--tags", tags])
    return cmd


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
        print(
            "WARNING: fdroidcl not found (brew install fdroidcl) — F-Droid repo sync will fail",
            file=sys.stderr,
        )
    if needs_apkeep and not shutil.which("apkeep"):
        print(
            "WARNING: apkeep not found (brew install apkeep) — Aurora auto-install will fail",
            file=sys.stderr,
        )


def run_playbook(*, limit: list[str], check: bool, tags: str | None) -> int:
    cmd = build_playbook_argv(limit=limit, check=check, tags=tags)
    return subprocess.run(cmd, env=repo_env(), cwd=REPO_ROOT).returncode


def run_import_catalog(host: str) -> tuple[int, str]:
    if not IMPORT_CATALOG.is_file():
        return 0, ""
    print(f"\n=== Obtainium catalog import: {host} ===")
    result = subprocess.run(
        [sys.executable, str(IMPORT_CATALOG), host, "all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.returncode != 0:
        print(f"FAIL: Obtainium import failed on {host} (exit {result.returncode})", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.rstrip(), file=sys.stderr)
        return result.returncode, "obtainium import"
    return 0, ""


def run_configure_aurora(host: str) -> tuple[int, str]:
    if not CONFIGURE_AURORA.is_file():
        return 0, ""
    print(f"\n=== Aurora first-run setup: {host} ===")
    for attempt in (1, 2):
        result = subprocess.run([str(CONFIGURE_AURORA), host], cwd=REPO_ROOT, capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.returncode == 0:
            return 0, ""
        if attempt == 1:
            print(f"Retrying Aurora configuration on {host}...")
            time.sleep(3)
    print(f"FAIL: Aurora setup failed on {host} (exit {result.returncode})", file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode or 1, "aurora setup"


def run_enable_autojs6_shizuku(host: str) -> tuple[int, str]:
    if not ENABLE_AUTOJS6_SHIZUKU.is_file():
        return 0, ""
    print(f"\n=== AutoJs6 Shizuku drawer: {host} ===")
    for attempt in (1, 2):
        result = subprocess.run(
            [sys.executable, str(ENABLE_AUTOJS6_SHIZUKU), host],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.returncode == 0:
            return 0, ""
        if attempt == 1:
            print(f"Retrying AutoJs6 Shizuku enable on {host}...")
            time.sleep(3)
    print(f"FAIL: AutoJs6 Shizuku enable failed on {host} (exit {result.returncode})", file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode or 1, "autojs6 shizuku"


def run_harden_fleet_apps(host: str) -> tuple[int, str]:
    if not HARDEN_FLEET_APPS.is_file():
        return 0, ""
    print(f"\n=== Fleet app privileges: {host} ===")
    result = subprocess.run(
        [sys.executable, str(HARDEN_FLEET_APPS), host],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.returncode == 0:
        return 0, ""
    print(f"FAIL: Fleet app hardening failed on {host} (exit {result.returncode})", file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode or 1, "fleet app privileges"


def deploy(scope: Scope, hosts: list[str], *, check: bool) -> int:
    require_ansible()
    warn_prerequisites(scope)
    install_collections()

    targets = resolve_hosts(hosts)
    rc = run_playbook(limit=targets, check=check, tags=scope.ansible_tags)

    if rc != 0 or check:
        return rc

    failures: list[str] = []
    if scope is Scope.FULL:
        for host in targets:
            step_rc, step = run_import_catalog(host)
            if step_rc != 0:
                rc = step_rc
                failures.append(f"{host}: {step}")
        if rc != 0 and failures:
            print("\nPost-deploy failures:", file=sys.stderr)
            for item in failures:
                print(f"  - {item}", file=sys.stderr)
            return rc

        print("\n=== App stores (F-Droid + Play) post-import ===")
        rc = run_playbook(limit=targets, check=False, tags=Scope.APP_STORES.ansible_tags)
        if rc != 0:
            return rc

    if scope in (Scope.FULL, Scope.PLAY):
        for host in targets:
            step_rc, step = run_harden_fleet_apps(host)
            if step_rc != 0:
                rc = step_rc
                failures.append(f"{host}: {step}")
        for host in targets:
            step_rc, step = run_configure_aurora(host)
            if step_rc != 0:
                rc = step_rc
                failures.append(f"{host}: {step}")

    if scope is Scope.FULL:
        for host in targets:
            step_rc, step = run_enable_autojs6_shizuku(host)
            if step_rc != 0:
                rc = step_rc
                failures.append(f"{host}: {step}")

    if failures:
        print("\nPost-deploy failures:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)

    return rc


def print_footer(rc: int, scope: Scope) -> None:
    print()
    if rc != 0:
        print(f"Fleet deploy finished with errors (exit {rc}). Failed hosts are listed above.", file=sys.stderr)
    elif scope is Scope.FDROID:
        print("Fdroid deploy complete. Install an app: ANDROID_SERIAL=<target> fdroidcl install <appid>")
    elif scope is Scope.PLAY:
        print(
            "Play deploy complete. Aurora Store is installed, granted Shizuku, "
            "using Shizuku installer, and set for automatic installs."
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
        help="Deploy scope (default: full phased fleet deploy)",
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
