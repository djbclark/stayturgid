"""Shared site-overlay and private-companion discovery.

All product entry points use this module for the implicit portion of site
selection.  Explicit ``ANSIBLE_CONFIG`` and ``STAYTURGID_SITE_DIR`` handling
stays with the caller, while Stage 0 dual-read (``frdminc/tendcf#98``) and the
legacy ``OPS_ROOT/.mysite`` + ``site-*`` fallback contract are defined here once:

- ``tendcf`` multi-site layout (``TENDCF_OPS_ROOT`` default ``~/tendcf-ops``):
  deterministic slug-based pairing of ``tendcf-public-<slug>`` (Ansible overlay)
  and ``tendcf-private-<slug>`` (private companion) selected via
  ``TENDCF_SITE`` or ``$XDG_CONFIG_HOME/tendcf/active-site`` (else
  ``~/.config/tendcf/active-site``).  Fail-closed: never globs a sole directory
  under ``~/tendcf-ops``, rejects symlinks / case mismatches / invalid slugs /
  ``-wt`` worktrees, and never creates legacy ``site-private`` inside
  ``~/tendcf-ops``.
- Legacy ``~/ops`` layout (``OPS_ROOT`` default ``~/ops``): ``OPS_ROOT/.mysite``
  then exactly one qualifying ``site-*`` or ``tendcf-public-*`` checkout,
  excluding reserved ``site-private*`` / ``tendcf-private*`` companions and
  deduplicating Stage 2 bridge symlinks by resolved target.
"""

from __future__ import annotations

import errno
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

DEFAULT_PRIVATE_COMPANION_NAME = "site-private"
RESERVED_PRIVATE_NAME = DEFAULT_PRIVATE_COMPANION_NAME
PRIVATE_PREFIX = "site-private-"
PUBLIC_PREFIX = "site-public-"

TENDCF_OPS_ROOT_NAME = "tendcf-ops"
LEGACY_OPS_ROOT_NAME = "ops"
TENDCF_PRIVATE_NAME = "tendcf-private"
TENDCF_PRIVATE_PREFIX = "tendcf-private-"
TENDCF_PUBLIC_PREFIX = "tendcf-public-"
MAX_SITE_SLUG_LENGTH = 64
MAX_ACTIVE_SITE_BYTES = 4096
WORKTREE_SUFFIX = "-wt"

# Lowercase ASCII slug: `\Z` (not `$`) refuses a trailing newline.
SITE_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")

PRIVATE_RESERVATION_HINT = (
    "site-private* is reserved for private companions (and tendcf-private* in ~/tendcf-ops); "
    "use site-public-<operator> or tendcf-public-<site> for an overlay."
)


class SiteDiscoveryError(RuntimeError):
    """The configured ops topology cannot select a single site overlay."""


class _NoActiveTendcfSiteError(SiteDiscoveryError):
    """Internal marker: tendcf-ops is active without an explicit site selector."""


@dataclass(frozen=True)
class SiteSelection:
    """A selected site directory and the precedence step that selected it."""

    path: Path
    source: str
    slug: str | None = None
    private_dir: Path | None = None


def _env_map(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _home_dir(env: Mapping[str, str]) -> Path:
    raw = env.get("HOME", "")
    if raw and "\x00" not in raw:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
    return Path.home()


def _expand_home_path(raw: str, env: Mapping[str, str], *, label: str) -> Path:
    """Expand strictly ``~`` and ``~/...`` against ``_home_dir``; reject NUL and ``~user``."""

    if not isinstance(raw, str) or not raw:
        raise SiteDiscoveryError(f"{label} must not be empty")
    if "\x00" in raw:
        raise SiteDiscoveryError(f"{label} contains a NUL byte")
    if raw == "~":
        return _home_dir(env)
    if raw.startswith("~/"):
        rest = raw[2:]
        if not rest or rest.startswith("/"):
            raise SiteDiscoveryError(f"Malformed tilde path in {label}: {raw!r}")
        return _home_dir(env) / rest
    if raw.startswith("~"):
        raise SiteDiscoveryError(f"Unsupported tilde user expansion in {label}: {raw!r}")
    return Path(raw)


def _has_explicit_legacy_ops_root(env: Mapping[str, str]) -> bool:
    return bool(env.get("OPS_ROOT", "").strip())


def validate_site_slug(slug: str, *, label: str = "site slug") -> str:
    """Validate ``<site>`` slug grammar (``^[a-z][a-z0-9]*(?:-[a-z0-9]+)*\\Z``, <=64 chars, no ``-wt``)."""

    if not isinstance(slug, str) or not slug:
        raise SiteDiscoveryError(f"{label} must not be empty")
    if "\x00" in slug:
        raise SiteDiscoveryError(f"{label} contains a NUL byte")
    if len(slug) > MAX_SITE_SLUG_LENGTH:
        raise SiteDiscoveryError(f"{label} {slug!r} exceeds maximum length of {MAX_SITE_SLUG_LENGTH} characters")
    if not SITE_SLUG_RE.match(slug):
        raise SiteDiscoveryError(f"Invalid {label} {slug!r}")
    if slug.endswith(WORKTREE_SUFFIX):
        raise SiteDiscoveryError(f"Invalid {label} {slug!r}: suffix {WORKTREE_SUFFIX!r} is reserved for worktrees")
    return slug


def extract_tendcf_public_slug(name: str) -> str | None:
    """Return the validated slug when *name* is ``tendcf-public-<slug>``, else ``None``."""

    if not name.startswith(TENDCF_PUBLIC_PREFIX):
        return None
    candidate = name[len(TENDCF_PUBLIC_PREFIX) :]
    try:
        return validate_site_slug(candidate, label="tendcf-public slug")
    except SiteDiscoveryError:
        return None


def active_site_config_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return ``$XDG_CONFIG_HOME/tendcf/active-site`` (when absolute), else ``~/.config/tendcf/active-site``."""

    env = _env_map(environ)
    raw = env.get("XDG_CONFIG_HOME", "")
    if raw and "\x00" not in raw:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate / "tendcf" / "active-site"
    return _home_dir(env) / ".config" / "tendcf" / "active-site"


def read_active_site_file(path: Path) -> str | None:
    """Read a plain single-line non-symlink active-site file; return ``None`` if absent, fail closed if invalid."""

    try:
        is_link = path.is_symlink()
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot inspect active-site config {path}: {exc}") from exc
    if is_link:
        raise SiteDiscoveryError(f"active-site config must not be a symlink: {path}")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)):
            raise SiteDiscoveryError(f"active-site config must not be a symlink: {path}") from exc
        raise SiteDiscoveryError(f"Cannot read active-site config {path}: {exc}") from exc

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SiteDiscoveryError(f"active-site config must be a regular file: {path}")
        if st.st_size > MAX_ACTIVE_SITE_BYTES:
            raise SiteDiscoveryError(f"active-site config exceeds {MAX_ACTIVE_SITE_BYTES} bytes: {path}")
        fh = os.fdopen(fd, "rb")
    except SiteDiscoveryError:
        os.close(fd)
        raise
    except OSError as exc:
        os.close(fd)
        raise SiteDiscoveryError(f"Cannot inspect active-site config {path}: {exc}") from exc
    except BaseException:
        os.close(fd)
        raise

    with fh:
        try:
            data = fh.read(MAX_ACTIVE_SITE_BYTES + 1)
        except OSError as exc:
            raise SiteDiscoveryError(f"Cannot read active-site config {path}: {exc}") from exc

    if len(data) > MAX_ACTIVE_SITE_BYTES:
        raise SiteDiscoveryError(f"active-site config exceeds {MAX_ACTIVE_SITE_BYTES} bytes: {path}")
    if b"\x00" in data:
        raise SiteDiscoveryError(f"active-site config contains a NUL byte: {path}")
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SiteDiscoveryError(f"active-site config is not valid UTF-8: {path}: {exc}") from exc

    normalized = raw.replace("\r\n", "\n")
    if "\r" in normalized:
        raise SiteDiscoveryError(f"active-site config contains bare CR characters: {path}")

    entries: list[str] = []
    for line in normalized.split("\n"):
        stripped = line.strip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(stripped)

    if not entries:
        raise SiteDiscoveryError(f"active-site config has no site slug: {path}")
    if len(entries) > 1:
        raise SiteDiscoveryError(f"active-site config is ambiguous ({len(entries)} entries): {path}")
    return validate_site_slug(entries[0], label=f"site slug in {path}")


def _explicit_tendcf_ops_root(env: Mapping[str, str]) -> Path | None:
    """Return validated ``TENDCF_OPS_ROOT`` when set, else ``None``; fail closed on invalid values."""

    if "TENDCF_OPS_ROOT" not in env:
        return None
    raw = env["TENDCF_OPS_ROOT"]
    if not raw.strip():
        raise SiteDiscoveryError("TENDCF_OPS_ROOT is set but empty; unset it or set an absolute path.")
    expanded = _expand_home_path(raw.strip(), env, label="TENDCF_OPS_ROOT")
    if not expanded.is_absolute() or ".." in expanded.parts:
        raise SiteDiscoveryError(f"TENDCF_OPS_ROOT must be an absolute path without '..': {raw!r}")
    return expanded.resolve()


def _resolve_tendcf_selector(
    env: Mapping[str, str],
    *,
    allow_active_site_file: bool = True,
) -> tuple[str | None, str | None]:
    """Resolve ``TENDCF_SITE`` > XDG ``active-site``; fail closed on malformed inputs."""

    if "TENDCF_SITE" in env:
        slug = validate_site_slug(env["TENDCF_SITE"], label="TENDCF_SITE")
        return slug, "TENDCF_SITE"

    if not allow_active_site_file:
        return None, None
    # An explicit legacy OPS_ROOT without TENDCF_OPS_ROOT/TENDCF_SITE stays isolated
    # from the operator's host ~/.config/tendcf/active-site file.
    if _has_explicit_legacy_ops_root(env) and "TENDCF_OPS_ROOT" not in env:
        return None, None

    cfg = active_site_config_path(env)
    file_slug = read_active_site_file(cfg)
    if file_slug is not None:
        return file_slug, f"active-site ({cfg})"
    return None, None


def _check_exact_site_dir(root: Path, name: str, *, required: bool) -> Path | None:
    """Verify ``<root>/<name>`` is an exact-case real directory inside *root* (no symlinks)."""

    exact = None
    case_mismatch = None
    target_lower = name.lower()
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name == name:
                    exact = entry
                    break
                if case_mismatch is None and entry.name.lower() == target_lower:
                    case_mismatch = entry
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot read ops root {root}: {exc}") from exc

    if exact is None:
        if case_mismatch is not None:
            raise SiteDiscoveryError(f"Wrong directory casing for {name!r} under {root}: found {case_mismatch.name!r}")
        if required:
            raise SiteDiscoveryError(f"Required site directory not found: {root / name}")
        return None

    candidate = Path(exact.path)
    try:
        is_link = exact.is_symlink()
        is_dir = exact.is_dir(follow_symlinks=False)
        entry_st = exact.stat(follow_symlinks=False)
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot inspect site directory {candidate}: {exc}") from exc

    if is_link:
        raise SiteDiscoveryError(f"Site directory must not be a symlink under tendcf-ops: {candidate}")
    if not is_dir:
        raise SiteDiscoveryError(f"Site path is not a directory: {candidate}")

    open_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(candidate, open_flags)
        fd_st = os.fstat(fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)):
            raise SiteDiscoveryError(f"Site directory must not be a symlink under tendcf-ops: {candidate}") from exc
        raise SiteDiscoveryError(f"Cannot open site directory {candidate}: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)

    if not stat.S_ISDIR(fd_st.st_mode):
        raise SiteDiscoveryError(f"Site path is not a directory: {candidate}")
    if (fd_st.st_dev, fd_st.st_ino) != (entry_st.st_dev, entry_st.st_ino):
        raise SiteDiscoveryError(f"Site directory identity changed during lookup: {candidate}")

    try:
        resolved = candidate.resolve(strict=True)
        resolved_st = os.lstat(resolved)
    except (OSError, RuntimeError) as exc:
        raise SiteDiscoveryError(f"Cannot resolve site directory {candidate}: {exc}") from exc
    if resolved.parent != root or resolved.name != name:
        raise SiteDiscoveryError(f"Site directory resolves outside {root}: {resolved}")
    if (resolved_st.st_dev, resolved_st.st_ino) != (fd_st.st_dev, fd_st.st_ino):
        raise SiteDiscoveryError(f"Site directory resolved identity mismatch: {resolved}")
    return resolved


def _infer_explicit_site_dir(env: Mapping[str, str]) -> Path | None:
    explicit_config = env.get("ANSIBLE_CONFIG", "").strip()
    if explicit_config:
        cfg = _expand_home_path(explicit_config, env, label="ANSIBLE_CONFIG")
        cfg = cfg.resolve() if cfg.is_absolute() else (Path.cwd() / cfg).resolve()
        return cfg.parent
    explicit_site = env.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit_site:
        return _expand_home_path(explicit_site, env, label="STAYTURGID_SITE_DIR").resolve()
    return None


def _resolve_configured_private_dir(env: Mapping[str, str], root: Path) -> Path | None:
    raw = env.get("STAYTURGID_PRIVATE_DIR", "").strip()
    if not raw:
        return None
    configured = _expand_home_path(raw, env, label="STAYTURGID_PRIVATE_DIR")
    return configured.resolve() if configured.is_absolute() else (root / configured).resolve()


def _ensure_no_private_pairing_drift(
    env: Mapping[str, str],
    root: Path,
    paired_private: Path,
    *,
    slug: str,
) -> None:
    configured = _resolve_configured_private_dir(env, root)
    if configured is not None and configured != paired_private.resolve():
        raise SiteDiscoveryError(
            f"Cross-site pairing mismatch for site {slug!r}: STAYTURGID_PRIVATE_DIR ({configured}) "
            f"does not match paired private companion {paired_private}."
        )


def _selector_root_and_strictness(env: Mapping[str, str]) -> tuple[Path, bool]:
    """Return ``(root, strict_tendcf_only)`` for deterministic slug-based pairing."""

    explicit_tendcf = _explicit_tendcf_ops_root(env)
    if explicit_tendcf is not None:
        return explicit_tendcf, True
    if _has_explicit_legacy_ops_root(env):
        return _expand_home_path(env["OPS_ROOT"].strip(), env, label="OPS_ROOT").resolve(), False
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    if default_tendcf.is_dir():
        return default_tendcf.resolve(), True
    default_legacy = _home_dir(env) / LEGACY_OPS_ROOT_NAME
    if default_legacy.is_dir():
        return default_legacy.resolve(), False
    return default_tendcf.resolve(), True


def _resolve_paired_paths_for_slug(
    root: Path,
    slug: str,
    *,
    strict_tendcf_only: bool,
) -> tuple[Path, Path]:
    """Resolve deterministic ``(public_overlay, private_companion)`` pair for *slug* under *root*."""

    if not root.is_dir():
        raise SiteDiscoveryError(
            f"Ops root is not a directory: {root}. Set TENDCF_OPS_ROOT/OPS_ROOT or create the configured ops workspace."
        )
    resolved_root = root.resolve(strict=True)
    tendcf_pub_name = f"{TENDCF_PUBLIC_PREFIX}{slug}"
    tendcf_priv_name = f"{TENDCF_PRIVATE_PREFIX}{slug}"

    if strict_tendcf_only:
        pub = _check_exact_site_dir(resolved_root, tendcf_pub_name, required=True)
        assert pub is not None
        priv_existing = _check_exact_site_dir(resolved_root, tendcf_priv_name, required=False)
        priv = priv_existing if priv_existing is not None else (resolved_root / tendcf_priv_name)
        return pub, priv

    # Legacy OPS_ROOT transition mode (Stage 0/2): accept either tendcf-{public,private}-<slug>
    # or site-{public,private}-<slug>, failing closed if both point to distinct directories.
    tendcf_pub = resolved_root / tendcf_pub_name
    site_pub = resolved_root / f"{PUBLIC_PREFIX}{slug}"
    tendcf_exists = tendcf_pub.is_dir()
    site_exists = site_pub.is_dir()

    if tendcf_exists and site_exists:
        r_tendcf = tendcf_pub.resolve()
        r_site = site_pub.resolve()
        if r_tendcf != r_site:
            raise SiteDiscoveryError(
                f"Ambiguous site overlay for slug {slug!r} under {resolved_root}: "
                f"both {tendcf_pub} and {site_pub} exist and point to different directories."
            )
        pub = r_tendcf
        prefer_tendcf = not tendcf_pub.is_symlink() or site_pub.is_symlink()
    elif tendcf_exists:
        pub = tendcf_pub.resolve()
        prefer_tendcf = True
    elif site_exists:
        pub = site_pub.resolve()
        prefer_tendcf = False
    else:
        raise SiteDiscoveryError(
            f"No site overlay found for slug {slug!r} under {resolved_root} "
            f"(expected {tendcf_pub_name} or {PUBLIC_PREFIX}{slug})."
        )

    tendcf_priv = resolved_root / tendcf_priv_name
    site_priv = resolved_root / f"{PRIVATE_PREFIX}{slug}"
    if tendcf_priv.exists() and site_priv.exists():
        if tendcf_priv.resolve() != site_priv.resolve():
            raise SiteDiscoveryError(
                f"Ambiguous private companion for slug {slug!r} under {resolved_root}: "
                f"both {tendcf_priv} and {site_priv} exist and point to different directories."
            )
        priv = tendcf_priv.resolve()
    elif tendcf_priv.exists():
        priv = tendcf_priv.resolve()
    elif site_priv.exists():
        priv = site_priv.resolve()
    else:
        priv = tendcf_priv if prefer_tendcf else site_priv
    return pub, priv


def ops_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the active ops root (``TENDCF_OPS_ROOT`` > ``OPS_ROOT`` > ``~/tendcf-ops`` if present > ``~/ops``)."""

    env = _env_map(environ)
    explicit_tendcf = _explicit_tendcf_ops_root(env)
    if explicit_tendcf is not None:
        return explicit_tendcf
    raw = env.get("OPS_ROOT", "").strip()
    if raw:
        return _expand_home_path(raw, env, label="OPS_ROOT").resolve()
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    if default_tendcf.is_dir():
        return default_tendcf.resolve()
    return (_home_dir(env) / LEGACY_OPS_ROOT_NAME).resolve()


def private_companion_path(
    environ: Mapping[str, str] | None = None,
    *,
    site_dir: Path | None = None,
) -> Path:
    """Return the paired or configured private-companion path.

    - In ``tendcf`` pair-bound mode (``TENDCF_SITE``, XDG ``active-site``, or an
      explicit ``tendcf-public-<slug>`` overlay), returns the deterministic
      matched ``tendcf-private-<slug>`` (or ``site-private-<slug>`` during
      pre-move Stage 0 under ``~/ops``) and fails closed if
      ``STAYTURGID_PRIVATE_DIR`` drifts to a different path.
    - Never defaults to legacy ``site-private`` inside ``~/tendcf-ops``.
    - In legacy ``OPS_ROOT`` / ``~/ops`` mode, preserves ``STAYTURGID_PRIVATE_DIR``
      (resolved relative to ``OPS_ROOT``) and the ``OPS_ROOT/site-private`` default.
    """

    env = _env_map(environ)
    explicit_site = site_dir.expanduser().resolve() if site_dir is not None else _infer_explicit_site_dir(env)

    # 1. Explicit tendcf-public-<slug> site_dir deterministically pairs with sibling tendcf-private-<slug>.
    explicit_slug = extract_tendcf_public_slug(explicit_site.name) if explicit_site is not None else None

    # 2. Explicit TENDCF_SITE or XDG active-site selector (skip host active-site when explicit
    #    ANSIBLE_CONFIG/STAYTURGID_SITE_DIR is used without TENDCF_OPS_ROOT/TENDCF_SITE).
    allow_active_file = explicit_site is None or "TENDCF_OPS_ROOT" in env
    selector_slug, _source = _resolve_tendcf_selector(env, allow_active_site_file=allow_active_file)

    if selector_slug is not None:
        if explicit_site is not None and explicit_slug is not None and explicit_slug != selector_slug:
            raise SiteDiscoveryError(
                f"Cross-site pairing mismatch: selected site {selector_slug!r} does not match "
                f"overlay {explicit_site.name!r} (slug {explicit_slug!r})."
            )
        root, strict_tendcf = _selector_root_and_strictness(env)
        if strict_tendcf:
            paired = root / f"{TENDCF_PRIVATE_PREFIX}{selector_slug}"
        else:
            tendcf_priv = root / f"{TENDCF_PRIVATE_PREFIX}{selector_slug}"
            tendcf_pub = root / f"{TENDCF_PUBLIC_PREFIX}{selector_slug}"
            site_priv = root / f"{PRIVATE_PREFIX}{selector_slug}"
            if tendcf_priv.exists() and site_priv.exists() and tendcf_priv.resolve() != site_priv.resolve():
                raise SiteDiscoveryError(
                    f"Ambiguous private companion for slug {selector_slug!r} under {root}: "
                    f"both {tendcf_priv} and {site_priv} exist and point to different directories."
                )
            if tendcf_priv.exists() or tendcf_pub.exists():
                paired = tendcf_priv
            else:
                paired = site_priv
        _ensure_no_private_pairing_drift(env, root, paired, slug=selector_slug)
        return paired

    if explicit_slug is not None and explicit_site is not None:
        paired = explicit_site.parent / f"{TENDCF_PRIVATE_PREFIX}{explicit_slug}"
        _ensure_no_private_pairing_drift(env, explicit_site.parent, paired, slug=explicit_slug)
        return paired

    # 3. Legacy / explicit STAYTURGID_PRIVATE_DIR.
    root = ops_root(env)
    configured = _resolve_configured_private_dir(env, root)
    if configured is not None:
        return configured

    # 4. Refuse creating legacy site-private inside ~/tendcf-ops or explicit TENDCF_OPS_ROOT.
    explicit_tendcf = _explicit_tendcf_ops_root(env)
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    in_tendcf_root = explicit_tendcf is not None or (not _has_explicit_legacy_ops_root(env) and default_tendcf.is_dir())
    if in_tendcf_root:
        if explicit_site is not None and explicit_tendcf is None:
            # Caller explicitly passed an arbitrary ANSIBLE_CONFIG / STAYTURGID_SITE_DIR
            # outside tendcf-public-<slug>; keep legacy companion under ~/ops instead of
            # polluting ~/tendcf-ops with site-private.
            return (_home_dir(env) / LEGACY_OPS_ROOT_NAME).resolve() / DEFAULT_PRIVATE_COMPANION_NAME
        raise _NoActiveTendcfSiteError(
            f"No active tendcf site selected for {root}: refusing to default to legacy "
            f"{DEFAULT_PRIVATE_COMPANION_NAME!r} under tendcf-ops. "
            "Set TENDCF_SITE=<site>, write ~/.config/tendcf/active-site, or set STAYTURGID_PRIVATE_DIR."
        )

    return root / DEFAULT_PRIVATE_COMPANION_NAME


def ensure_private_companion(
    environ: Mapping[str, str] | None = None,
    *,
    site_dir: Path | None = None,
) -> Path:
    """Ensure the private-companion directory exists without inventing content.

    A missing directory is created locally with owner-only permissions.  This
    deliberately does not initialize Git, clone a private remote, or create
    secrets: those choices are operator-specific.
    """

    env = _env_map(environ)
    path = private_companion_path(env, site_dir=site_dir)
    if path.name.startswith(TENDCF_PRIVATE_PREFIX) and path.parent.is_dir():
        # If it already exists under tendcf-ops, validate exact-case non-symlink real dir.
        _check_exact_site_dir(path.parent.resolve(strict=True), path.name, required=False)
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot create private companion directory {path}: {exc}") from exc
    if path.is_symlink() and path.name.startswith(TENDCF_PRIVATE_PREFIX):
        raise SiteDiscoveryError(f"Private companion must not be a symlink: {path}")
    if not path.is_dir():
        raise SiteDiscoveryError(f"Private companion path is not a directory: {path}")
    return path


def is_reserved_private_name(name: str) -> bool:
    """True for legacy ``site-private`` / ``site-private-*`` or ``tendcf-private`` / ``tendcf-private-*``."""

    return (
        name == RESERVED_PRIVATE_NAME
        or name.startswith(PRIVATE_PREFIX)
        or name == TENDCF_PRIVATE_NAME
        or name.startswith(TENDCF_PRIVATE_PREFIX)
    )


def reject_private_companion_overlay(
    path: Path,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Fail when a selected overlay is a reserved or configured private companion."""

    resolved = path.expanduser().resolve()
    if is_reserved_private_name(resolved.name):
        raise SiteDiscoveryError(
            f"Selected site overlay {resolved} is reserved for the private companion. "
            f"{PRIVATE_RESERVATION_HINT} Set ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite."
        )
    env = _env_map(environ)
    try:
        private_dir = private_companion_path(env, site_dir=resolved).resolve()
    except _NoActiveTendcfSiteError:
        return
    if resolved == private_dir:
        raise SiteDiscoveryError(
            f"Selected site overlay {resolved} is reserved for the private companion. "
            f"{PRIVATE_RESERVATION_HINT} Set ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite."
        )


def resolve_site_selection(
    environ: Mapping[str, str] | None = None,
    *,
    require_ansible_config: bool = False,
) -> SiteSelection:
    """Resolve the active site overlay via Stage 0 dual-read or legacy ``OPS_ROOT`` discovery.

    Precedence:
    1. Pair-bound ``tendcf`` selector (``TENDCF_SITE`` > XDG ``active-site`` when
       not isolated by explicit legacy ``OPS_ROOT``).
    2. Fail closed if ``TENDCF_OPS_ROOT`` is set or ``~/tendcf-ops`` exists
       (without explicit legacy ``OPS_ROOT``) and no selector is configured —
       never globs a sole directory under ``~/tendcf-ops``.
    3. Legacy ``OPS_ROOT/.mysite``, then exactly one qualifying ``site-*`` or
       ``tendcf-public-*`` checkout under ``OPS_ROOT`` (default ``~/ops``),
       excluding reserved private companions and ``-wt`` worktrees, and
       deduplicating Stage 2 bridge symlinks by resolved target.
    """

    env = _env_map(environ)

    # 1. Deterministic pair-bound tendcf selector (TENDCF_SITE or XDG active-site).
    selector_slug, selector_source = _resolve_tendcf_selector(env)
    if selector_slug is not None and selector_source is not None:
        root, strict_tendcf = _selector_root_and_strictness(env)
        pub, priv = _resolve_paired_paths_for_slug(root, selector_slug, strict_tendcf_only=strict_tendcf)
        _ensure_no_private_pairing_drift(env, root, priv, slug=selector_slug)
        if require_ansible_config and not (pub / "ansible.cfg").is_file():
            raise SiteDiscoveryError(
                f"Selected {selector_source} site overlay is missing ansible.cfg: {pub / 'ansible.cfg'}"
            )
        ensured_priv = ensure_private_companion(env, site_dir=pub)
        return SiteSelection(
            path=pub,
            source=selector_source,
            slug=selector_slug,
            private_dir=ensured_priv,
        )

    # 2. If tendcf-ops is active without a selector, fail closed (never glob ~/tendcf-ops).
    explicit_tendcf = _explicit_tendcf_ops_root(env)
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    if explicit_tendcf is not None or (not _has_explicit_legacy_ops_root(env) and default_tendcf.is_dir()):
        active_root = explicit_tendcf if explicit_tendcf is not None else default_tendcf.resolve()
        cfg = active_site_config_path(env)
        raise SiteDiscoveryError(
            f"No active tendcf site selected for {active_root}: tendcf-ops never globs a sole directory. "
            f"Set TENDCF_SITE=<site>, write {cfg}, or set ANSIBLE_CONFIG / STAYTURGID_SITE_DIR."
        )

    # 3. Legacy OPS_ROOT (or ~/ops) path.
    root = ops_root(env)
    private_dir = ensure_private_companion(env).resolve()

    mysite = root / ".mysite"
    if mysite.is_dir():
        selected = mysite.resolve()
        reject_private_companion_overlay(selected, env)
        return SiteSelection(path=selected, source="OPS_ROOT/.mysite", private_dir=private_dir)
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

    candidates_by_resolved: dict[Path, str] = {}
    for pattern, source_label in (
        ("site-*", "site-* discovery"),
        (f"{TENDCF_PUBLIC_PREFIX}*", "tendcf-public-* discovery"),
    ):
        for candidate in sorted(root.glob(pattern)):
            if is_reserved_private_name(candidate.name) or candidate.name.endswith(WORKTREE_SUFFIX):
                continue
            if candidate.name.startswith(TENDCF_PUBLIC_PREFIX) and extract_tendcf_public_slug(candidate.name) is None:
                continue
            if not candidate.is_dir():
                continue
            try:
                resolved = candidate.resolve()
                if is_reserved_private_name(resolved.name) or resolved == private_dir:
                    continue
            except OSError:
                continue
            if require_ansible_config and not (candidate / "ansible.cfg").is_file():
                continue
            # Deduplicate Stage 2 bridge symlinks pointing to the same physical overlay;
            # keep the first label (site-* discovery) when a legacy name matches first.
            candidates_by_resolved.setdefault(resolved, source_label)

    if len(candidates_by_resolved) == 1:
        selected_path, source_label = next(iter(candidates_by_resolved.items()))
        discovered_slug = extract_tendcf_public_slug(selected_path.name)
        paired_private = private_dir
        if discovered_slug is not None and _resolve_configured_private_dir(env, root) is None:
            candidate_priv = root / f"{TENDCF_PRIVATE_PREFIX}{discovered_slug}"
            if candidate_priv.is_dir():
                paired_private = candidate_priv.resolve()
        return SiteSelection(
            path=selected_path,
            source=source_label,
            slug=discovered_slug,
            private_dir=paired_private,
        )

    knobs = "ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite"
    qualifier = " with an ansible.cfg" if require_ansible_config else ""
    if not candidates_by_resolved:
        raise SiteDiscoveryError(
            f"No site overlay found: {root} contains no qualifying site-* or tendcf-public-* checkout{qualifier} "
            f"({PRIVATE_RESERVATION_HINT}). Set {knobs}."
        )
    listing = ", ".join(str(candidate) for candidate in candidates_by_resolved)
    raise SiteDiscoveryError(
        f"Ambiguous site overlay: multiple qualifying site-* / tendcf-public-* checkouts under {root} ({listing}). "
        f"{PRIVATE_RESERVATION_HINT} Set {knobs}."
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
