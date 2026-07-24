"""Shared site-overlay and private-companion discovery.

All product entry points use this module for the implicit portion of site
selection.  Explicit ``ANSIBLE_CONFIG`` and ``STAYTURGID_SITE_DIR`` handling
stays with the caller, but the ``OPS_ROOT/.mysite`` and ``site-*`` fallback
contract is defined here once.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

DEFAULT_PRIVATE_COMPANION_NAME = "site-private"


class SiteDiscoveryError(RuntimeError):
    """The configured ops topology cannot select a single site overlay."""


@dataclass(frozen=True)
class SiteSelection:
    """A selected site directory and the precedence step that selected it."""

    path: Path
    source: str


def ops_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the configured ops root (default ``~/ops``)."""

    env = os.environ if environ is None else environ
    raw = env.get("OPS_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else (Path.home() / "ops").resolve()


def private_companion_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the configurable private-companion path.

    Relative ``STAYTURGID_PRIVATE_DIR`` values are resolved under ``OPS_ROOT``.
    The default remains ``OPS_ROOT/site-private``.
    """

    env = os.environ if environ is None else environ
    root = ops_root(env)
    raw = env.get("STAYTURGID_PRIVATE_DIR", "").strip()
    if not raw:
        return root / DEFAULT_PRIVATE_COMPANION_NAME
    configured = Path(raw).expanduser()
    return configured.resolve() if configured.is_absolute() else (root / configured).resolve()


def ensure_private_companion(environ: Mapping[str, str] | None = None) -> Path:
    """Ensure the private-companion directory exists without inventing content.

    A missing directory is created locally with owner-only permissions.  This
    deliberately does not initialize Git, clone a private remote, or create
    secrets: those choices are operator-specific.
    """

    path = private_companion_path(environ)
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot create private companion directory {path}: {exc}") from exc
    if not path.is_dir():
        raise SiteDiscoveryError(f"Private companion path is not a directory: {path}")
    return path


def reject_private_companion_overlay(
    path: Path,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Fail when a selected overlay is the reserved private companion."""

    resolved = path.expanduser().resolve()
    private_dir = private_companion_path(environ).resolve()
    if resolved.name == DEFAULT_PRIVATE_COMPANION_NAME or resolved == private_dir:
        raise SiteDiscoveryError(
            f"Selected site overlay {resolved} is reserved for the private companion, not a site overlay."
        )


def resolve_site_selection(
    environ: Mapping[str, str] | None = None,
    *,
    require_ansible_config: bool = False,
) -> SiteSelection:
    """Resolve ``.mysite`` or exactly one qualifying ``site-*`` checkout.

    The private companion is ensured first and excluded both by its configured
    path and by the reserved literal name ``site-private``.
    """

    env = os.environ if environ is None else environ
    root = ops_root(env)
    private_dir = ensure_private_companion(env).resolve()

    mysite = root / ".mysite"
    if mysite.is_dir():
        selected = mysite.resolve()
        reject_private_companion_overlay(selected, env)
        return SiteSelection(path=selected, source="OPS_ROOT/.mysite")
    if mysite.exists() or mysite.is_symlink():
        raise SiteDiscoveryError(
            f"{mysite} exists but does not resolve to a directory. "
            "Fix or remove .mysite, or set STAYTURGID_SITE_DIR/ANSIBLE_CONFIG explicitly."
        )

    if not root.is_dir():
        raise SiteDiscoveryError(
            f"OPS_ROOT is not a directory: {root}. "
            "Set STAYTURGID_SITE_DIR/ANSIBLE_CONFIG explicitly or create OPS_ROOT."
        )

    candidates: list[Path] = []
    for candidate in sorted(root.glob("site-*")):
        if candidate.name == DEFAULT_PRIVATE_COMPANION_NAME or not candidate.is_dir():
            continue
        try:
            if candidate.resolve() == private_dir:
                continue
        except OSError:
            continue
        if require_ansible_config and not (candidate / "ansible.cfg").is_file():
            continue
        candidates.append(candidate.resolve())

    if len(candidates) == 1:
        return SiteSelection(path=candidates[0], source="site-* discovery")
    knobs = "ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite"
    qualifier = " with an ansible.cfg" if require_ansible_config else ""
    if not candidates:
        raise SiteDiscoveryError(
            f"No site overlay found: {root} contains no qualifying site-* checkout{qualifier} "
            f"(site-private is reserved). Set {knobs}."
        )
    listing = ", ".join(str(candidate) for candidate in candidates)
    raise SiteDiscoveryError(
        f"Ambiguous site overlay: multiple qualifying site-* checkouts under {root} ({listing}). Set {knobs}."
    )


def announce_site_selection(
    selection: SiteSelection,
    *,
    stream: TextIO | None = None,
    command: str = "stayturgid",
) -> None:
    """Print the selected site directory and precedence source."""

    output = sys.stderr if stream is None else stream
    print(f"{command}: site directory {selection.path} (source: {selection.source})", file=output)
