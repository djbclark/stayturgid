"""Resolve the Ansible site overlay used by product-side entry points.

The public checkout ships only a generic inventory example.  Real deployments
therefore select a private site's ``ansible.cfg`` by explicit ``ANSIBLE_CONFIG``,
by ``STAYTURGID_SITE_DIR``, or by discovering exactly one ``site-*`` overlay
checkout under ``OPS_ROOT`` (default ``~/ops``).  There is no operator-specific
default: ambiguous or absent discovery fails with instructions instead of
silently selecting a site.
"""

from __future__ import annotations

import configparser
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class AnsibleConfigError(RuntimeError):
    """The selected Ansible configuration cannot be used for a deployment."""


@dataclass(frozen=True)
class AnsibleContext:
    """Resolved configuration paths for one product invocation."""

    config: Path
    inventory: Path
    collections_path: Path
    source: str


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


def _discover_site_config(env: Mapping[str, str]) -> Path:
    """Return the single discovered ``site-*`` overlay ``ansible.cfg``.

    Scans ``OPS_ROOT`` (default ``~/ops``) for sibling ``site-*`` checkouts
    that carry an ``ansible.cfg``.  Exactly one match is unambiguous; zero or
    multiple matches must be resolved by the operator — never by a hardcoded
    site default.
    """

    ops_root = Path(env.get("OPS_ROOT", "~/ops")).expanduser()
    candidates = sorted(p / "ansible.cfg" for p in ops_root.glob("site-*") if (p / "ansible.cfg").is_file())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise AnsibleConfigError(
            f"No site overlay found: {ops_root} contains no site-* checkout with an "
            "ansible.cfg. Set ANSIBLE_CONFIG or STAYTURGID_SITE_DIR to select a "
            "configuration explicitly."
        )
    listing = ", ".join(str(c.parent) for c in candidates)
    raise AnsibleConfigError(
        f"Ambiguous site overlay: multiple site-* checkouts under {ops_root} "
        f"({listing}). Set ANSIBLE_CONFIG or STAYTURGID_SITE_DIR to select one."
    )


def resolve_ansible_context(
    repo_root: Path,
    environ: Mapping[str, str] | None = None,
) -> AnsibleContext:
    """Return the explicit, site-directory, or discovered-overlay Ansible context.

    ``ANSIBLE_CONFIG`` always wins.  When it is absent, ``STAYTURGID_SITE_DIR``
    selects the overlay directory explicitly; otherwise exactly one ``site-*``
    checkout under ``OPS_ROOT`` (default ``~/ops``) is discovered.  Zero or
    multiple discovery matches raise instead of silently picking a default.
    """

    env = os.environ if environ is None else environ
    explicit = env.get("ANSIBLE_CONFIG", "").strip()
    site_dir_value = env.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit:
        config = _expand_path(explicit, base=Path.cwd()).resolve()
        source = "ANSIBLE_CONFIG"
    elif site_dir_value:
        config = (Path(site_dir_value).expanduser() / "ansible.cfg").resolve()
        source = "STAYTURGID_SITE_DIR"
    else:
        config = _discover_site_config(env).resolve()
        source = "site overlay"

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

    return AnsibleContext(
        config=config,
        inventory=inventory,
        collections_path=collections_path,
        source=source,
    )


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
