#!/usr/bin/env python3
"""Fleet deploy orchestration via ansible/playbooks/site.yml.

Canonical entry (from repo root)::

  ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/site.yml

This wrapper installs collections and, by default, re-runs control_node/site.yml after
the fleet site playbook. Ansible ``--limit`` is device hosts only, so localhost
(control node) would otherwise be skipped — Mac agents/launchd must still refresh.
Pass ``--devices-only`` (#57) to skip that second pass when iterating on one device.

Usage:
  deploy_fleet.py [host ...]              # full site deploy
  deploy_fleet.py --scope fdroid oneui-device      # F-Droid roles only
  deploy_fleet.py --scope play oneui-device        # Play roles
  deploy_fleet.py --devices-only oneui-device      # skip the redundant Mac control_node pass
  deploy_fleet.py --scope bootstrap-apks --devices-only oneui-device
                                                    # APK ensure/verify/Shizuku-start only (#166) --
                                                    # skips termux_userland/post-ui/validate/control_node
                                                    # entirely; use for a pure app version bump
  CHECK=1 deploy_fleet.py oneui-device             # ansible --check --diff (no post-UI / validate asserts)

Scopes map to ansible-playbook --tags on site.yml (see site.yml header).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib.ansible_context import (
    AnsibleConfigError,
    require_fresh_checkout,
    require_inventory,
    require_limit_hosts,
    resolve_ansible_context,
    resolved_env,
)
from control.lib.fleet_deploy_lock import FleetLockHeld, fleet_lock
from control.lib.secretspec_exec import secretspec_run
from control.lib.fleet_targets import FLEET_STATUS_VAR, offline_hosts, parse_inventory_hosts
from control.lib.fleet_targets import inventory_list as _inventory_list

SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
MAC_SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "control_node" / "site.yml"
REQUIREMENTS = REPO_ROOT / "ansible" / "requirements.yml"

# Wall-clock cap per ansible-playbook invocation. Historical full-fleet runs
# take ~13-15 minutes; this gives a ~2x margin for one genuine retry without
# letting a hung or endlessly-retrying rollout run indefinitely (see #104).
# Override with STAYTURGID_DEPLOY_TIMEOUT_SECONDS for unusually large fleets.
DEPLOY_TIMEOUT_SECONDS = int(os.environ.get("STAYTURGID_DEPLOY_TIMEOUT_SECONDS", "1800"))


class Scope(str, Enum):
    FULL = "full"
    FDROID = "fdroid"
    PLAY = "play"
    APP_STORES = "app-stores"
    BOOTSTRAP_APKS = "bootstrap-apks"

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
    # Canonicalizing the selected path preserves the caller's choice while
    # making relative ANSIBLE_CONFIG values reliable from any product recipe.
    env = resolved_env(REPO_ROOT)
    load_play_env(env)
    return env


def check_mode(cli_check: bool) -> bool:
    return cli_check or os.environ.get("CHECK", "0") == "1"


def inventory_list(group: str = "stayturgid") -> dict:
    """Compatibility wrapper for callers and tests of this entry point."""

    return _inventory_list(REPO_ROOT, group)


def inventory_hosts(group: str = "stayturgid") -> list[str]:
    return parse_inventory_hosts(inventory_list(group), group)


def resolve_hosts(hosts: list[str]) -> list[str]:
    if hosts:
        # Explicit hosts on the command line are an intentional override —
        # never filtered, even if marked offline.
        return hosts
    data = inventory_list()
    all_hosts = parse_inventory_hosts(data)
    skipped = offline_hosts(data, all_hosts)
    if skipped:
        print(
            f"deploy_fleet.py: skipping offline host(s) {', '.join(skipped)} "
            f"({FLEET_STATUS_VAR}: offline) — pass explicitly to override",
            file=sys.stderr,
        )
    return [h for h in all_hosts if h not in skipped]


def require_ansible() -> None:
    if not shutil.which("ansible-playbook"):
        print("ERROR: ansible-playbook not found (brew install ansible)", file=sys.stderr)
        sys.exit(1)
    if not shutil.which("secretspec"):
        print("ERROR: secretspec not found (brew install secretspec)", file=sys.stderr)
        sys.exit(1)


def _requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def _collections_up_to_date(collections_path: Path, stamp: Path, current_hash: str) -> bool:
    if not (collections_path / "ansible_collections").is_dir():
        return False
    try:
        return stamp.read_text().strip() == current_hash
    except OSError:
        return False


def install_collections() -> None:
    context = resolve_ansible_context(REPO_ROOT)
    current_hash = _requirements_hash()
    stamp = context.collections_path / ".requirements-hash"
    # #57: ansible-galaxy pays real dependency-resolution/filesystem-check cost
    # on every invocation — skip it when requirements.yml hasn't changed since
    # the last successful install.
    if _collections_up_to_date(context.collections_path, stamp, current_hash):
        return
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
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(current_hash)


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
            "WARNING: apkeep not found (brew install apkeep) — Play app installs will fail",
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
    # Inventory belongs to the active site config, while product files always
    # belong to this checkout. Passing the latter explicitly prevents roles
    # from inferring the product root from an overlay's ansible.cfg path.
    cmd = secretspec_run(
        "ansible-playbook",
        str(playbook),
        "-e",
        f"stayturgid_repo_root={REPO_ROOT}",
    )
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
    try:
        return subprocess.run(cmd, env=repo_env(), cwd=REPO_ROOT, timeout=DEPLOY_TIMEOUT_SECONDS).returncode
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: {playbook.name} exceeded {DEPLOY_TIMEOUT_SECONDS}s wall-clock cap — aborted. "
            f"Override with STAYTURGID_DEPLOY_TIMEOUT_SECONDS if this fleet genuinely needs longer.",
            file=sys.stderr,
        )
        return 124


def deploy_mac(*, check: bool, tags: str = "mac", verbose: int = 0) -> int:
    """Mac localhost playbooks are not affected by device --limit."""
    return run_playbook(
        MAC_SITE_PLAYBOOK,
        check=check,
        tags=tags,
        verbose=verbose,
    )


def deploy(scope: Scope, hosts: list[str], *, check: bool, verbose: int = 0, devices_only: bool = False) -> int:
    require_ansible()
    context = resolve_ansible_context(REPO_ROOT)
    require_inventory(context)
    require_fresh_checkout(REPO_ROOT)
    warn_prerequisites(scope)
    install_collections()

    targets = resolve_hosts(hosts)
    if not targets:
        # An empty limit string falls back to "all" in require_limit_hosts,
        # which would silently deploy to every host — the opposite of
        # intended when every host happens to be marked offline.
        print(
            "ERROR: every fleet host is marked offline and none were passed explicitly — nothing to deploy",
            file=sys.stderr,
        )
        return 1
    # A limit that matches no inventory hosts must fail loudly instead of
    # letting an empty play report a green deploy.
    require_limit_hosts(context, ",".join(targets))
    # preflight.yml owns SSH bootstrap; skip the redundant bootstrap.yml pass in
    # both normal deploys and dry runs.
    skip_bootstrap = "bootstrap"
    label = "deploy_fleet.py %s" % (",".join(targets) or "(whole fleet)")
    if check:
        # #184: dry-run recaps look like real deploys (ok/changed/failed=0) and
        # were misread as "fleet is current" after ops-v1.2.0. Banner both ends.
        print(
            "NOTE: CHECK MODE (ansible --check --diff) — no APK installs, no "
            "device writes, no Mac control_node apply. A green recap here does "
            "NOT mean the fleet converged; run `just deploy` (without "
            "deploy-check) to apply.",
            file=sys.stderr,
        )
    with fleet_lock(label):
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
        if devices_only:
            # #57: the caller only wants the device playbook (e.g. iterating on
            # one device) — skip the second ansible-playbook launch entirely.
            return rc
        # Always refresh Mac control node on real deploys: deploy_fleet always passes a
        # device --limit, so site.yml's control_node import never selects localhost.
        mac_rc = deploy_mac(check=False, verbose=verbose)
        return rc if rc != 0 else mac_rc


def print_footer(rc: int, scope: Scope, *, check: bool = False) -> None:
    print()
    if check:
        if rc != 0:
            print(
                f"Fleet deploy-check (DRY RUN) finished with errors (exit {rc}). No changes were applied.",
                file=sys.stderr,
            )
        else:
            print(
                "Fleet deploy-check (DRY RUN) complete — no changes were applied "
                "to devices or the Mac. A green Ansible recap in check mode only "
                "means the plan was valid, not that APKs/config converged. "
                "Apply with: just deploy"
            )
        return
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
        "--devices-only",
        action="store_true",
        help="Skip the control_node/site.yml Mac pass (#57) — for iterating on one device only",
    )
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

    check = check_mode(args.check)
    try:
        rc = deploy(scope, args.hosts, check=check, verbose=verbose, devices_only=args.devices_only)
    except FleetLockHeld as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print_footer(rc, scope, check=check)
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
