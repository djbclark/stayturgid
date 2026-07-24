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

    @property
    def site_dir(self) -> Path:
        """Directory containing the selected site Ansible configuration."""

        return self.config.parent


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
    inventory = _expand_path(inventory_value, base=config.parent).resolve()

    collections_value = _config_value(config, "collections_path")
    if collections_value:
        first_collection_path = collections_value.split(os.pathsep, 1)[0]
        collections_path = _expand_path(first_collection_path, base=config.parent).resolve()
    else:
        collections_path = (repo_root / ".ansible" / "collections").resolve()

    context = AnsibleContext(
        config=config,
        inventory=inventory,
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
    return env


def require_limit_hosts(context: AnsibleContext, limit: str) -> list[str]:
    """Return the hosts the resolved inventory matches for *limit*; never zero.

    A limit that matches no hosts means the wrong configuration was selected
    (or the alias is unknown); succeeding with an empty play would report a
    deploy/verify as green without touching any device.
    """

    require_inventory(context)
    result = subprocess.run(
        ["ansible", "--list-hosts", "-i", str(context.inventory), limit or "all"],
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
            f"{context.source} config {context.config} (inventory {context.inventory}). "
            "Check the host alias or point ANSIBLE_CONFIG/STAYTURGID_SITE_DIR at the "
            "intended site overlay."
        )
    return hosts


def require_inventory(context: AnsibleContext) -> None:
    """Fail before a real invocation when the selected inventory is absent."""

    if context.inventory.exists():
        return
    raise AnsibleConfigError(
        f"Selected {context.source} config {context.config} refers to missing inventory "
        f"{context.inventory}. Live deploys require a site overlay; set ANSIBLE_CONFIG "
        "or STAYTURGID_SITE_DIR."
    )
