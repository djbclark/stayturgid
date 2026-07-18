"""Resolve the Ansible site overlay used by product-side entry points.

The public checkout ships only a generic inventory example.  Real deployments
therefore select a private site's ``ansible.cfg`` by explicit ``ANSIBLE_CONFIG``
or, when unset, by the conventional ``STAYTURGID_SITE_DIR`` overlay.
"""

from __future__ import annotations

import configparser
import os
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


def resolve_ansible_context(
    repo_root: Path,
    environ: Mapping[str, str] | None = None,
) -> AnsibleContext:
    """Return the explicit, site-default, or generic-upstream Ansible context.

    ``ANSIBLE_CONFIG`` always wins.  When it is absent, the private overlay
    directory can be set with ``STAYTURGID_SITE_DIR``; its default is kept out
    of the public inventory and is only a conventional local checkout path.
    """

    env = os.environ if environ is None else environ
    explicit = env.get("ANSIBLE_CONFIG", "").strip()
    if explicit:
        config = _expand_path(explicit, base=Path.cwd()).resolve()
        source = "ANSIBLE_CONFIG"
    else:
        site_dir = Path(env.get("STAYTURGID_SITE_DIR", "~/ops/site-djbclark")).expanduser()
        site_config = site_dir / "ansible.cfg"
        if site_config.is_file():
            config = site_config.resolve()
            source = "site overlay"
        else:
            config = (repo_root / "ansible" / "ansible.cfg").resolve()
            source = "upstream fallback"

    if not config.is_file():
        if source == "ANSIBLE_CONFIG":
            raise AnsibleConfigError(f"ANSIBLE_CONFIG points to a missing file: {config}")
        raise AnsibleConfigError(f"Selected {source} Ansible config is missing: {config}")

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


def require_inventory(context: AnsibleContext) -> None:
    """Fail before a real invocation when the selected inventory is absent."""

    if context.inventory.exists():
        return
    raise AnsibleConfigError(
        f"Selected {context.source} config {context.config} refers to missing inventory "
        f"{context.inventory}. Live deploys require a site overlay; set ANSIBLE_CONFIG "
        "or STAYTURGID_SITE_DIR."
    )
