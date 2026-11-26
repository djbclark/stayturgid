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


def _safe_resolve(path: Path, *, label: str, strict: bool = False) -> Path:
    """Resolve *path* and map filesystem / symlink-loop errors to ``SiteDiscoveryError``."""

    try:
        return path.resolve(strict=strict)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SiteDiscoveryError(f"Cannot resolve {label} {path}: {exc}") from exc


def _paths_equal_or_samefile(left: Path, right: Path) -> bool:
    """True when *left* and *right* match by path or refer to the same inode (handles APFS casing)."""

    if left == right:
        return True
    try:
        if left.exists() and right.exists() and os.path.samefile(left, right):
            return True
    except OSError:
        pass
    return False


def expand_user_path(
    raw: str,
    environ: Mapping[str, str] | None = None,
    *,
    label: str = "path",
) -> Path:
    """Expand ``~`` / ``~/...`` against ``environ['HOME']``; reject NUL bytes and ``~otheruser``."""

    env = _env_map(environ)
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


def has_explicit_tendcf_config(environ: Mapping[str, str] | None = None) -> bool:
    """True when ``TENDCF_SITE`` or ``TENDCF_OPS_ROOT`` is explicitly present in *environ*."""

    env = _env_map(environ)
    return "TENDCF_SITE" in env or "TENDCF_OPS_ROOT" in env


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


def extract_public_overlay_slug(name: str) -> tuple[str, str] | None:
    """Return ``(family, slug)`` for ``tendcf-public-<slug>`` or ``site-public-<slug>``, else ``None``."""

    for family, prefix in (("tendcf", TENDCF_PUBLIC_PREFIX), ("site", PUBLIC_PREFIX)):
        if name.startswith(prefix):
            candidate = name[len(prefix) :]
            try:
                return family, validate_site_slug(candidate, label=f"{prefix} slug")
            except SiteDiscoveryError:
                return None
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
    if not raw or raw != raw.strip():
        raise SiteDiscoveryError(
            f"TENDCF_OPS_ROOT must be a non-empty path without leading/trailing whitespace: {raw!r}"
        )
    expanded = expand_user_path(raw, env, label="TENDCF_OPS_ROOT")
    if not expanded.is_absolute() or ".." in expanded.parts:
        raise SiteDiscoveryError(f"TENDCF_OPS_ROOT must be an absolute path without '..': {raw!r}")
    return _safe_resolve(expanded, label="TENDCF_OPS_ROOT")


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

    resolved = _safe_resolve(candidate, label="site directory", strict=True)
    try:
        resolved_st = os.lstat(resolved)
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot stat resolved site directory {resolved}: {exc}") from exc
    if resolved.parent != root or resolved.name != name:
        raise SiteDiscoveryError(f"Site directory resolves outside {root}: {resolved}")
    if (resolved_st.st_dev, resolved_st.st_ino) != (fd_st.st_dev, fd_st.st_ino):
        raise SiteDiscoveryError(f"Site directory resolved identity mismatch: {resolved}")
    return resolved


def _infer_explicit_site_dir(env: Mapping[str, str]) -> Path | None:
    explicit_config = env.get("ANSIBLE_CONFIG", "").strip()
    if explicit_config:
        cfg = expand_user_path(explicit_config, env, label="ANSIBLE_CONFIG")
        cfg = _safe_resolve(cfg if cfg.is_absolute() else (Path.cwd() / cfg), label="ANSIBLE_CONFIG")
        return cfg.parent
    explicit_site = env.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit_site:
        raw_site = expand_user_path(explicit_site, env, label="STAYTURGID_SITE_DIR")
        return _safe_resolve(raw_site, label="STAYTURGID_SITE_DIR")
    return None


def _resolve_configured_private_dir(env: Mapping[str, str], root: Path) -> Path | None:
    raw = env.get("STAYTURGID_PRIVATE_DIR", "").strip()
    if not raw:
        return None
    configured = expand_user_path(raw, env, label="STAYTURGID_PRIVATE_DIR")
    target = configured if configured.is_absolute() else (root / configured)
    return _safe_resolve(target, label="STAYTURGID_PRIVATE_DIR")


def _ensure_no_private_pairing_drift(
    env: Mapping[str, str],
    root: Path,
    paired_private: Path,
    *,
    slug: str,
) -> None:
    configured = _resolve_configured_private_dir(env, root)
    if configured is None:
        return
    paired_resolved = _safe_resolve(paired_private, label="paired private companion")
    if not _paths_equal_or_samefile(configured, paired_resolved):
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
        raw_ops = expand_user_path(env["OPS_ROOT"].strip(), env, label="OPS_ROOT")
        return _safe_resolve(raw_ops, label="OPS_ROOT"), False
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    if default_tendcf.is_dir():
        return _safe_resolve(default_tendcf, label="tendcf-ops root"), True
    default_legacy = _home_dir(env) / LEGACY_OPS_ROOT_NAME
    if default_legacy.is_dir():
        return _safe_resolve(default_legacy, label="ops root"), False
    return _safe_resolve(default_tendcf, label="tendcf-ops root"), True


def _resolve_legacy_slug_private(root: Path, slug: str, *, prefer_tendcf: bool) -> Path:
    """Resolve the paired private companion for *slug* under a legacy ``OPS_ROOT`` / ``~/ops``.

    Shared by both ``_resolve_paired_paths_for_slug`` and ``private_companion_path`` so
    Stage 0/2 partial renames never invent a second empty private companion directory.
    """

    tendcf_priv = root / f"{TENDCF_PRIVATE_PREFIX}{slug}"
    site_priv = root / f"{PRIVATE_PREFIX}{slug}"
    tendcf_exists = tendcf_priv.exists() or tendcf_priv.is_symlink()
    site_exists = site_priv.exists() or site_priv.is_symlink()

    if tendcf_exists and site_exists:
        r_tendcf = _safe_resolve(tendcf_priv, label="tendcf private companion")
        r_site = _safe_resolve(site_priv, label="site private companion")
        if not _paths_equal_or_samefile(r_tendcf, r_site):
            raise SiteDiscoveryError(
                f"Ambiguous private companion for slug {slug!r} under {root}: "
                f"both {tendcf_priv} and {site_priv} exist and point to different directories."
            )
        return r_tendcf
    if tendcf_exists:
        return _safe_resolve(tendcf_priv, label="tendcf private companion")
    if site_exists:
        return _safe_resolve(site_priv, label="site private companion")
    return tendcf_priv if prefer_tendcf else site_priv


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
    resolved_root = _safe_resolve(root, label="ops root", strict=True)
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
        r_tendcf = _safe_resolve(tendcf_pub, label="tendcf site overlay")
        r_site = _safe_resolve(site_pub, label="site overlay")
        if not _paths_equal_or_samefile(r_tendcf, r_site):
            raise SiteDiscoveryError(
                f"Ambiguous site overlay for slug {slug!r} under {resolved_root}: "
                f"both {tendcf_pub} and {site_pub} exist and point to different directories."
            )
        pub = r_tendcf
        prefer_tendcf = not tendcf_pub.is_symlink() or site_pub.is_symlink()
    elif tendcf_exists:
        pub = _safe_resolve(tendcf_pub, label="tendcf site overlay")
        prefer_tendcf = True
    elif site_exists:
        pub = _safe_resolve(site_pub, label="site overlay")
        prefer_tendcf = False
    else:
        raise SiteDiscoveryError(
            f"No site overlay found for slug {slug!r} under {resolved_root} "
            f"(expected {tendcf_pub_name} or {PUBLIC_PREFIX}{slug})."
        )

    priv = _resolve_legacy_slug_private(resolved_root, slug, prefer_tendcf=prefer_tendcf)
    if is_reserved_private_name(pub.name) or _paths_equal_or_samefile(
        pub, _safe_resolve(priv, label="private companion")
    ):
        raise SiteDiscoveryError(
            f"Selected site overlay {pub} is reserved for the private companion. {PRIVATE_RESERVATION_HINT}"
        )
    return pub, priv


def _strict_tendcf_root(env: Mapping[str, str]) -> Path | None:
    """Return the active strict ``tendcf-ops`` root when operating in strict mode, else ``None``."""

    explicit_tendcf = _explicit_tendcf_ops_root(env)
    if explicit_tendcf is not None:
        return explicit_tendcf
    if not _has_explicit_legacy_ops_root(env):
        default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
        if default_tendcf.is_dir():
            return _safe_resolve(default_tendcf, label="tendcf-ops root")
    return None


def is_strict_tendcf_root(environ: Mapping[str, str] | None = None) -> bool:
    """True when ``TENDCF_OPS_ROOT`` or an existing ``~/tendcf-ops`` (without explicit ``OPS_ROOT``) is active."""

    return _strict_tendcf_root(_env_map(environ)) is not None


def ops_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the active ops root (``TENDCF_OPS_ROOT`` > ``OPS_ROOT`` > ``~/tendcf-ops`` if present > ``~/ops``)."""

    env = _env_map(environ)
    explicit_tendcf = _explicit_tendcf_ops_root(env)
    if explicit_tendcf is not None:
        return explicit_tendcf
    raw = env.get("OPS_ROOT", "").strip()
    if raw:
        return _safe_resolve(expand_user_path(raw, env, label="OPS_ROOT"), label="OPS_ROOT")
    default_tendcf = _home_dir(env) / TENDCF_OPS_ROOT_NAME
    if default_tendcf.is_dir():
        return _safe_resolve(default_tendcf, label="tendcf-ops root")
    return _safe_resolve(_home_dir(env) / LEGACY_OPS_ROOT_NAME, label="ops root")


def private_companion_path(
    environ: Mapping[str, str] | None = None,
    *,
    site_dir: Path | None = None,
) -> Path:
    """Return the paired or configured private-companion path.

    - In ``tendcf`` pair-bound mode (``TENDCF_SITE``, XDG ``active-site``, or an
      explicit ``tendcf-public-<slug>`` overlay), returns the deterministic
      matched ``tendcf-private-<slug>`` (or ``site-private-<slug>`` during
      pre-move Stage 0 under ``~/ops``) and fails closed on cross-slug,
      cross-root, or ``STAYTURGID_PRIVATE_DIR`` drift.
    - Never defaults to legacy ``site-private`` inside ``~/tendcf-ops``.
    - In legacy ``OPS_ROOT`` / ``~/ops`` mode, preserves ``STAYTURGID_PRIVATE_DIR``
      (resolved relative to ``OPS_ROOT``) and the ``OPS_ROOT/site-private`` default.
    """

    env = _env_map(environ)
    explicit_site = (
        _safe_resolve(site_dir.expanduser(), label="site directory")
        if site_dir is not None
        else _infer_explicit_site_dir(env)
    )

    explicit_parsed = extract_public_overlay_slug(explicit_site.name) if explicit_site is not None else None
    explicit_family = explicit_parsed[0] if explicit_parsed is not None else None
    explicit_slug = explicit_parsed[1] if explicit_parsed is not None else None

    # Skip host active-site when explicit ANSIBLE_CONFIG / STAYTURGID_SITE_DIR is used
    # without TENDCF_OPS_ROOT / TENDCF_SITE.
    allow_active_file = explicit_site is None or "TENDCF_OPS_ROOT" in env
    selector_slug, _source = _resolve_tendcf_selector(env, allow_active_site_file=allow_active_file)

    if selector_slug is not None:
        root, strict_tendcf = _selector_root_and_strictness(env)
        if explicit_site is not None and explicit_slug is not None:
            if explicit_slug != selector_slug:
                raise SiteDiscoveryError(
                    f"Cross-site pairing mismatch: selected site {selector_slug!r} does not match "
                    f"overlay {explicit_site.name!r} (slug {explicit_slug!r})."
                )
            if not _paths_equal_or_samefile(explicit_site.parent, root):
                raise SiteDiscoveryError(
                    f"Cross-root pairing mismatch for site {selector_slug!r}: overlay parent "
                    f"{explicit_site.parent} does not match active ops root {root}."
                )
        if strict_tendcf:
            paired = root / f"{TENDCF_PRIVATE_PREFIX}{selector_slug}"
        else:
            tendcf_pub = root / f"{TENDCF_PUBLIC_PREFIX}{selector_slug}"
            site_pub = root / f"{PUBLIC_PREFIX}{selector_slug}"
            prefer_tendcf = tendcf_pub.is_dir() and (not site_pub.is_dir() or not tendcf_pub.is_symlink())
            paired = _resolve_legacy_slug_private(root, selector_slug, prefer_tendcf=prefer_tendcf)
        _ensure_no_private_pairing_drift(env, root, paired, slug=selector_slug)
        return paired

    if explicit_site is not None and explicit_family == "tendcf" and explicit_slug is not None:
        strict_root = _strict_tendcf_root(env)
        in_strict_parent = strict_root is not None and _paths_equal_or_samefile(explicit_site.parent, strict_root)
        if in_strict_parent:
            paired = explicit_site.parent / f"{TENDCF_PRIVATE_PREFIX}{explicit_slug}"
        else:
            paired = _resolve_legacy_slug_private(explicit_site.parent, explicit_slug, prefer_tendcf=True)
        _ensure_no_private_pairing_drift(env, explicit_site.parent, paired, slug=explicit_slug)
        return paired

    # Legacy / explicit STAYTURGID_PRIVATE_DIR.
    root = ops_root(env)
    configured = _resolve_configured_private_dir(env, root)
    if configured is not None:
        return configured

    # Refuse creating legacy site-private inside ~/tendcf-ops or explicit TENDCF_OPS_ROOT.
    if _strict_tendcf_root(env) is not None:
        if explicit_site is not None:
            # Explicit ANSIBLE_CONFIG / STAYTURGID_SITE_DIR / dir= outside tendcf-public-<slug>
            # stays functional without polluting ~/tendcf-ops with a legacy site-private dir.
            return (
                _safe_resolve(_home_dir(env) / LEGACY_OPS_ROOT_NAME, label="ops root") / DEFAULT_PRIVATE_COMPANION_NAME
            )
        raise _NoActiveTendcfSiteError(
            f"No active tendcf site selected for {root}: refusing to default to legacy "
            f"{DEFAULT_PRIVATE_COMPANION_NAME!r} under tendcf-ops. "
            "Set TENDCF_SITE=<site>, write ~/.config/tendcf/active-site, or set STAYTURGID_PRIVATE_DIR."
        )

    return root / DEFAULT_PRIVATE_COMPANION_NAME


def _ensure_private_dir(path: Path, *, enforce_strict: bool) -> Path:
    """Create (0o700) and verify a resolved private-companion directory."""

    if enforce_strict and path.parent.is_dir():
        resolved_parent = _safe_resolve(path.parent, label="private companion parent", strict=True)
        _check_exact_site_dir(resolved_parent, path.name, required=False)

    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise SiteDiscoveryError(f"Cannot create private companion directory {path}: {exc}") from exc

    if enforce_strict:
        resolved_parent = _safe_resolve(path.parent, label="private companion parent", strict=True)
        verified = _check_exact_site_dir(resolved_parent, path.name, required=True)
        assert verified is not None
        return verified

    if not path.is_dir():
        raise SiteDiscoveryError(f"Private companion path is not a directory: {path}")
    return _safe_resolve(path, label="private companion")


def ensure_private_companion(
    environ: Mapping[str, str] | None = None,
    *,
    site_dir: Path | None = None,
    strict_tendcf: bool | None = None,
) -> Path:
    """Ensure the private-companion directory exists without inventing content.

    A missing directory is created locally with owner-only permissions.  This
    deliberately does not initialize Git, clone a private remote, or create
    secrets: those choices are operator-specific.
    """

    env = _env_map(environ)
    path = private_companion_path(env, site_dir=site_dir)
    strict_root = _strict_tendcf_root(env)
    enforce_strict = (
        strict_tendcf
        if strict_tendcf is not None
        else (
            strict_root is not None
            and path.name.startswith(TENDCF_PRIVATE_PREFIX)
            and _paths_equal_or_samefile(_safe_resolve(path.parent, label="private companion parent"), strict_root)
        )
    )
    return _ensure_private_dir(path, enforce_strict=enforce_strict)


def is_reserved_private_name(name: str) -> bool:
    """True (case-insensitively) for ``site-private`` / ``site-private-*`` or ``tendcf-private`` / ``tendcf-private-*``."""

    lowered = name.lower()
    return (
        lowered == RESERVED_PRIVATE_NAME
        or lowered.startswith(PRIVATE_PREFIX)
        or lowered == TENDCF_PRIVATE_NAME
        or lowered.startswith(TENDCF_PRIVATE_PREFIX)
    )


def reject_private_companion_overlay(
    path: Path,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Fail when a selected overlay is a reserved or configured private companion."""

    if is_reserved_private_name(path.name):
        raise SiteDiscoveryError(
            f"Selected site overlay {path} is reserved for the private companion. "
            f"{PRIVATE_RESERVATION_HINT} Set ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite."
        )
    resolved = _safe_resolve(path.expanduser(), label="site overlay")
    if is_reserved_private_name(resolved.name):
        raise SiteDiscoveryError(
            f"Selected site overlay {resolved} is reserved for the private companion. "
            f"{PRIVATE_RESERVATION_HINT} Set ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite."
        )
    env = _env_map(environ)
    try:
        private_dir = _safe_resolve(private_companion_path(env, site_dir=resolved), label="private companion")
    except _NoActiveTendcfSiteError:
        return
    if _paths_equal_or_samefile(resolved, private_dir):
        raise SiteDiscoveryError(
            f"Selected site overlay {resolved} is reserved for the private companion. "
            f"{PRIVATE_RESERVATION_HINT} Set ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite."
        )


def _pair_for_discovered_tendcf_overlay(
    selected_path: Path,
    root: Path,
    env: Mapping[str, str],
) -> tuple[str | None, Path | None]:
    """Return ``(slug, ensured_private_dir)`` if *selected_path* is ``tendcf-public-<slug>``."""

    slug = extract_tendcf_public_slug(selected_path.name)
    if slug is None or _resolve_configured_private_dir(env, root) is not None:
        return slug, None
    sibling_priv = selected_path.parent / f"{TENDCF_PRIVATE_PREFIX}{slug}"
    root_priv = root / f"{TENDCF_PRIVATE_PREFIX}{slug}"
    if sibling_priv.is_dir():
        return slug, _safe_resolve(sibling_priv, label="tendcf private companion")
    if not _paths_equal_or_samefile(selected_path.parent, root) and root_priv.is_dir():
        return slug, _safe_resolve(root_priv, label="tendcf private companion")
    legacy_sibling_priv = selected_path.parent / f"{PRIVATE_PREFIX}{slug}"
    if not (sibling_priv.exists() or sibling_priv.is_symlink()) and legacy_sibling_priv.is_dir():
        return slug, _safe_resolve(legacy_sibling_priv, label="site private companion")
    return slug, ensure_private_companion(env, site_dir=selected_path, strict_tendcf=False)


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
        reject_private_companion_overlay(pub, env)
        if require_ansible_config and not (pub / "ansible.cfg").is_file():
            raise SiteDiscoveryError(
                f"Selected {selector_source} site overlay is missing ansible.cfg: {pub / 'ansible.cfg'}"
            )
        ensured_priv = _ensure_private_dir(priv, enforce_strict=strict_tendcf)
        return SiteSelection(
            path=pub,
            source=selector_source,
            slug=selector_slug,
            private_dir=ensured_priv,
        )

    # 2. If tendcf-ops is active without a selector, fail closed (never glob ~/tendcf-ops).
    strict_root = _strict_tendcf_root(env)
    if strict_root is not None:
        cfg = active_site_config_path(env)
        raise SiteDiscoveryError(
            f"No active tendcf site selected for {strict_root}: tendcf-ops never globs a sole directory. "
            f"Set TENDCF_SITE=<site>, write {cfg}, or set ANSIBLE_CONFIG / STAYTURGID_SITE_DIR."
        )

    # 3. Legacy OPS_ROOT (or ~/ops) path.
    root = ops_root(env)
    configured_private = _resolve_configured_private_dir(env, root)
    expected_legacy_private = (
        configured_private if configured_private is not None else (root / DEFAULT_PRIVATE_COMPANION_NAME)
    )

    mysite = root / ".mysite"
    if mysite.is_dir():
        selected = _safe_resolve(mysite, label="OPS_ROOT/.mysite")
        reject_private_companion_overlay(selected, env)
        slug, tendcf_priv = _pair_for_discovered_tendcf_overlay(selected, root, env)
        if tendcf_priv is not None:
            return SiteSelection(path=selected, source="OPS_ROOT/.mysite", slug=slug, private_dir=tendcf_priv)
        private_dir = ensure_private_companion(env, strict_tendcf=False)
        return SiteSelection(path=selected, source="OPS_ROOT/.mysite", slug=slug, private_dir=private_dir)
    if mysite.exists() or mysite.is_symlink():
        ensure_private_companion(env, strict_tendcf=False)
        raise SiteDiscoveryError(
            f"{mysite} exists but does not resolve to a directory. "
            "Fix or remove .mysite, or set STAYTURGID_SITE_DIR/ANSIBLE_CONFIG explicitly."
        )

    if not root.is_dir():
        ensure_private_companion(env, strict_tendcf=False)
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
            except (OSError, RuntimeError):
                continue
            if is_reserved_private_name(resolved.name) or _paths_equal_or_samefile(resolved, expected_legacy_private):
                continue
            if require_ansible_config and not (candidate / "ansible.cfg").is_file():
                continue
            # Deduplicate Stage 2 bridge symlinks pointing to the same physical overlay;
            # keep the first label (site-* discovery) when a legacy name matches first.
            candidates_by_resolved.setdefault(resolved, source_label)

    if len(candidates_by_resolved) == 1:
        selected_path, source_label = next(iter(candidates_by_resolved.items()))
        discovered_slug, tendcf_priv = _pair_for_discovered_tendcf_overlay(selected_path, root, env)
        if tendcf_priv is not None:
            return SiteSelection(
                path=selected_path,
                source=source_label,
                slug=discovered_slug,
                private_dir=tendcf_priv,
            )
        private_dir = ensure_private_companion(env, strict_tendcf=False)
        return SiteSelection(
            path=selected_path,
            source=source_label,
            slug=discovered_slug,
            private_dir=private_dir,
        )

    ensure_private_companion(env, strict_tendcf=False)
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
