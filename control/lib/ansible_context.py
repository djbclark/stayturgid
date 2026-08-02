"""Resolve the Ansible site overlay used by product-side entry points."""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TextIO

if __package__:
    from .site_discovery import (
        SiteDiscoveryError,
        SiteSelection,
        announce_site_selection,
        ensure_private_companion,
        reject_private_companion_overlay,
        resolve_site_selection,
    )
else:  # direct import with control/lib on sys.path
    from site_discovery import (  # type: ignore[no-redef]
        SiteDiscoveryError,
        SiteSelection,
        announce_site_selection,
        ensure_private_companion,
        reject_private_companion_overlay,
        resolve_site_selection,
    )


class AnsibleConfigError(RuntimeError):
    """The selected Ansible configuration cannot be used for a deployment."""


@dataclass(frozen=True)
class AnsibleContext:
    """Resolved configuration paths for one product invocation."""

    config: Path
    inventory: Path
    collections_path: Path
    source: str
    inventories: tuple[Path, ...] = ()

    @property
    def site_dir(self) -> Path:
        """Directory containing the selected site Ansible configuration."""

        return self.config.parent

    def inventory_args(self) -> list[str]:
        """Return Ansible CLI arguments preserving all configured sources."""

        return [arg for path in self.inventory_paths for arg in ("-i", str(path))]

    @property
    def inventory_paths(self) -> tuple[Path, ...]:
        """Return every inventory source, including legacy single-source contexts."""

        return self.inventories or (self.inventory,)


def _expand_path(value: str, *, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _config_value(config: Path, name: str) -> str:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with config.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as exc:
        raise AnsibleConfigError(f"Cannot read Ansible config {config}: {exc}") from exc
    return parser.get("defaults", name, fallback="").strip()


def resolve_ansible_context(
    repo_root: Path,
    environ: Mapping[str, str] | None = None,
    *,
    announce: bool = True,
    announcement_stream: TextIO | None = None,
) -> AnsibleContext:
    """Return the explicit, site-directory, or discovered-overlay Ansible context.

    Precedence is ``ANSIBLE_CONFIG``, ``STAYTURGID_SITE_DIR``,
    ``OPS_ROOT/.mysite``, then exactly one qualifying ``site-*`` checkout.
    """

    env = os.environ if environ is None else environ
    try:
        ensure_private_companion(env)
    except SiteDiscoveryError as exc:
        raise AnsibleConfigError(str(exc)) from exc
    explicit = env.get("ANSIBLE_CONFIG", "").strip()
    site_dir_value = env.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit:
        config = _expand_path(explicit, base=Path.cwd()).resolve()
        source = "ANSIBLE_CONFIG"
        site_dir = config.parent
    elif site_dir_value:
        site_dir = Path(site_dir_value).expanduser().resolve()
        config = (site_dir / "ansible.cfg").resolve()
        source = "STAYTURGID_SITE_DIR"
    else:
        try:
            selection = resolve_site_selection(env, require_ansible_config=True)
        except SiteDiscoveryError as exc:
            raise AnsibleConfigError(str(exc)) from exc
        site_dir = selection.path
        config = (site_dir / "ansible.cfg").resolve()
        source = selection.source

    try:
        reject_private_companion_overlay(site_dir, env)
    except SiteDiscoveryError as exc:
        raise AnsibleConfigError(str(exc)) from exc

    if not config.is_file():
        if source == "ANSIBLE_CONFIG":
            raise AnsibleConfigError(f"ANSIBLE_CONFIG points to a missing file: {config}")
        raise AnsibleConfigError(
            f"Selected {source} Ansible config is missing: {config}. "
            "Set ANSIBLE_CONFIG or STAYTURGID_SITE_DIR to a valid site overlay."
        )

    inventory_value = _config_value(config, "inventory")
    if not inventory_value:
        raise AnsibleConfigError(f"Selected Ansible config has no [defaults] inventory: {config}")
    inventory_values = [item.strip() for item in inventory_value.split(",") if item.strip()]
    if not inventory_values:
        raise AnsibleConfigError(f"Selected Ansible config has no [defaults] inventory: {config}")
    inventories = tuple(_expand_path(item, base=config.parent).resolve() for item in inventory_values)
    # Compatibility for callers that need the site-owned host inventory rather
    # than the full precedence stack: Ansible applies later sources last.
    inventory = inventories[-1]

    collections_value = _config_value(config, "collections_path")
    if collections_value:
        first_collection_path = collections_value.split(os.pathsep, 1)[0]
        collections_path = _expand_path(first_collection_path, base=config.parent).resolve()
    else:
        collections_path = (repo_root / ".ansible" / "collections").resolve()

    context = AnsibleContext(
        config=config,
        inventory=inventory,
        inventories=inventories,
        collections_path=collections_path,
        source=source,
    )
    if announce:
        announce_site_selection(
            SiteSelection(path=context.site_dir, source=context.source),
            stream=sys.stderr if announcement_stream is None else announcement_stream,
        )
    return context


def resolved_env(repo_root: Path, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a subprocess environment pinned to the resolved Ansible context.

    Shared by every fleet entry point so no script can silently substitute the
    upstream config for the caller's selected site configuration.
    """

    env = dict(os.environ if environ is None else environ)
    context = resolve_ansible_context(repo_root, env)
    env["ANSIBLE_CONFIG"] = str(context.config)
    env["STAYTURGID_ROOT"] = str(repo_root)
    # Site configs intentionally contain no checkout-specific product paths.
    # Make every product entry point self-contained instead of relying on a
    # particular site justfile to have exported these search paths first.
    product_roles = str((repo_root / "ansible" / "roles").resolve())
    product_collections = (
        str((repo_root / ".ansible" / "collections").resolve()),
        str(repo_root.resolve()),
    )
    configured_roles = env.get("ANSIBLE_ROLES_PATH", "")
    configured_collections = env.get("ANSIBLE_COLLECTIONS_PATH", "")
    env["ANSIBLE_ROLES_PATH"] = os.pathsep.join(
        dict.fromkeys(path for path in (product_roles, *configured_roles.split(os.pathsep)) if path)
    )
    env["ANSIBLE_COLLECTIONS_PATH"] = os.pathsep.join(
        dict.fromkeys(path for path in (*product_collections, *configured_collections.split(os.pathsep)) if path)
    )
    # Real per-task timing (#57) regardless of which site's ansible.cfg is
    # selected — ansible.posix is already a required collection dependency.
    configured_callbacks = env.get("ANSIBLE_CALLBACKS_ENABLED", "")
    env["ANSIBLE_CALLBACKS_ENABLED"] = ",".join(
        dict.fromkeys(name for name in ("ansible.posix.profile_tasks", *configured_callbacks.split(",")) if name)
    )
    return env


def require_limit_hosts(context: AnsibleContext, limit: str) -> list[str]:
    """Return the hosts the resolved inventory matches for *limit*; never zero.

    A limit that matches no hosts means the wrong configuration was selected
    (or the alias is unknown); succeeding with an empty play would report a
    deploy/verify as green without touching any device.
    """

    require_inventory(context)
    result = subprocess.run(
        ["ansible", "--list-hosts", *context.inventory_args(), limit or "all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AnsibleConfigError(
            f"ansible --list-hosts failed for limit '{limit}' using {context.source} "
            f"config {context.config}:\n{result.stderr.strip()}"
        )
    hosts = [
        line.strip() for line in result.stdout.splitlines() if line.strip() and not line.lstrip().startswith("hosts (")
    ]
    if not hosts:
        raise AnsibleConfigError(
            f"Limit '{limit}' matches zero hosts in the inventory selected by "
            f"{context.source} config {context.config} "
            f"(inventories {', '.join(str(path) for path in context.inventory_paths)}). "
            "Check the host alias or point ANSIBLE_CONFIG/STAYTURGID_SITE_DIR at the "
            "intended site overlay."
        )
    return hosts


def require_inventory(context: AnsibleContext) -> None:
    """Fail before a real invocation when the selected inventory is absent."""

    missing = [path for path in context.inventory_paths if not path.exists()]
    if not missing:
        return
    raise AnsibleConfigError(
        f"Selected {context.source} config {context.config} refers to missing inventory "
        f"{', '.join(str(path) for path in missing)}. Live deploys require a site overlay; set ANSIBLE_CONFIG "
        "or STAYTURGID_SITE_DIR."
    )


def require_fresh_checkout(repo_root: Path, environ: Mapping[str, str] | None = None) -> None:
    """Fail before a real invocation when this product checkout is stale or dirty.

    A reference checkout like ``main/stayturgid`` (and its sibling product/site
    checkouts under the same worktree layout) is meant to be a pure, current
    mirror of ``origin/master`` — every live-apply
    ``just`` recipe reads its source of truth from whatever's on disk here.
    A stale or dirty checkout doesn't fail loudly; it just silently applies
    old (or locally-edited, uncommitted) content while everything looks like
    it worked. Confirmed real 2026-08-02: two fixes (hermes-gateway,
    fire-help) were merged upstream and appeared deployed — `ansible` ran,
    reported success, changed nothing — because this checkout was 10 commits
    behind `origin/master` and nobody had a way to notice short of manually
    diffing rendered output against what the source actually said.

    Set STAYTURGID_SKIP_FRESHNESS_CHECK=1 to bypass (e.g. intentionally
    testing against a pinned older commit). Network failures during the
    `git fetch` fail *open* (warn, don't block) rather than stranding offline
    use — staleness can't be verified without network, but that's a
    different, lower-stakes failure mode than a checkout silently going
    stale for weeks with the operator none the wiser.
    """

    env = os.environ if environ is None else environ
    if env.get("STAYTURGID_SKIP_FRESHNESS_CHECK", "").strip() == "1":
        return

    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=15,
        )

    if not (repo_root / ".git").exists():
        return  # Not a git checkout (e.g. an extracted tarball) — nothing to check.

    fetch = _git("fetch", "origin", "master", "--quiet")
    if fetch.returncode != 0:
        print(
            f"WARNING: could not fetch origin/master to check {repo_root} for staleness "
            f"({fetch.stderr.strip() or 'unknown error'}) — proceeding without the check.",
            file=sys.stderr,
        )
        return

    behind = _git("rev-list", "--count", "HEAD..origin/master")
    if behind.returncode == 0 and behind.stdout.strip().isdigit() and int(behind.stdout.strip()) > 0:
        n = behind.stdout.strip()
        raise AnsibleConfigError(
            f"{repo_root} is {n} commit(s) behind origin/master. Live-apply recipes read their "
            "source of truth from this checkout — a stale one silently re-applies old config "
            "instead of what you think you're deploying (this exact failure mode already caused "
            "a real incident, see require_fresh_checkout()'s docstring). Sync first:\n"
            f"  cd {repo_root} && git fetch origin master && git reset --hard origin/master\n"
            "Set STAYTURGID_SKIP_FRESHNESS_CHECK=1 to bypass intentionally."
        )

    status = _git("status", "--porcelain")
    if status.returncode == 0 and status.stdout.strip():
        raise AnsibleConfigError(
            f"{repo_root} has uncommitted changes. This checkout should normally be a pure "
            "mirror of origin/master — live-apply recipes will read your local edits as if "
            "they were the real deployed source, which is almost never what you want here. "
            "Commit/push from a task workspace instead (see AGENTS.md), or stash if this is "
            "a mistake:\n"
            f"  cd {repo_root} && git stash\n"
            "Set STAYTURGID_SKIP_FRESHNESS_CHECK=1 to bypass intentionally."
        )
