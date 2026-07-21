#!/usr/bin/env python3
"""Re-render product-owned generated files in a site overlay (Site Contract v1).

Implements ``site-sync`` (apply / dry-run / docs) and lockfile semantics per
``docs/architecture/site-contract.md`` §4 and acceptance test 3.

Exit codes:
    0  success / no-op
    1  precondition or input failure
    2  would overwrite drifted generated content (unless force-generated)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence, TextIO

from control.site_contract.site_map import SiteMap, SiteMapError, load_site_map

try:
    from jinja2 import Environment, StrictUndefined
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when deps missing
    raise SystemExit(
        "error: jinja2 is required for site-sync (install ansible-core, or use the project test venv: just test-venv)"
    ) from exc

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "error: PyYAML is required for site-sync (install ansible-core, or use the project test venv: just test-venv)"
    ) from exc

PRODUCT = "stayturgid"
CONTRACT_DIR = Path(__file__).resolve().parent
SYNC_TEMPLATE_DIR = CONTRACT_DIR / "sync_templates"
DEFAULT_MANIFEST_PATH = CONTRACT_DIR / "sync_manifest.yml"
REPO_ROOT = CONTRACT_DIR.parents[1]
LOCKFILE_RELATIVE = f"generated/{PRODUCT}/.lockfile.yml"
GENERATED_PREFIX = f"generated/{PRODUCT}/"

# D6 closed write set (design §2): inventory-derived content may only land in
# these fragment dirs (plus the lockfile), so a host add/remove/rename rewrites
# a bounded, reviewable file set. A template consuming ``inventory_hosts``
# outside this set is a projection bug — refused at plan time (exit 1).
PROJECTION_CLOSED_PREFIXES = tuple(f"generated/{PRODUCT}/fragments/{app}/" for app in ("caddy", "grafana", "olivetin"))
OLIVETIN_FRAGMENT_RELATIVE = f"generated/{PRODUCT}/fragments/olivetin/stayturgid_actions.yaml"

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_WOULD_OVERWRITE = 2

Mode = Literal["apply", "dry-run", "docs"]
ActionKind = Literal["create", "overwrite", "skip", "delete"]

# Generic paths/names only — docs mode must never emit operator identity.
_DOCS_PRODUCT_ROOT = f"/srv/products/{PRODUCT}"
_DOCS_SITE_DIR = "/srv/sites/site-example"
_DOCS_PRODUCT_VERSION = "0.0.0"
_DOCS_PRODUCT_COMMIT = "0000000000000000000000000000000000000000"
_DOCS_SYNCED = "1970-01-01T00:00:00Z"


class SiteSyncError(Exception):
    """Precondition or input failure for site-sync."""

    def __init__(self, message: str, *, exit_code: int = EXIT_PRECONDITION) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ForeignLiveConfigError(SiteSyncError):
    """Projection target exists but is not ours — would overwrite user content (exit 2)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=EXIT_WOULD_OVERWRITE)


@dataclass(frozen=True)
class ManifestEntry:
    """One product-owned generated file."""

    path: str
    template: str


@dataclass(frozen=True)
class SyncManifest:
    """Parsed product sync manifest."""

    contract_version: int
    product: str
    files: tuple[ManifestEntry, ...]

    def paths(self) -> frozenset[str]:
        return frozenset(entry.path for entry in self.files)


@dataclass(frozen=True)
class PlannedFile:
    """One planned action under generated/<product>/."""

    relative_path: str
    content: bytes | None  # None for delete
    action: ActionKind
    sha256: str | None = None  # of rendered content (None for delete)
    drift: bool = False  # true when on-disk hash != lockfile hash


@dataclass(frozen=True)
class SyncPlan:
    """Fully computed site-sync plan (no side effects until apply)."""

    destination: Path
    product_root: Path
    product_version: str
    product_commit: str
    synced: str
    files: tuple[PlannedFile, ...]
    lockfile_content: bytes
    lockfile_action: ActionKind

    @property
    def drifts(self) -> list[PlannedFile]:
        return [item for item in self.files if item.drift]

    @property
    def has_work(self) -> bool:
        if self.lockfile_action != "skip":
            return True
        return any(item.action != "skip" for item in self.files)


def _ops_root(env: Mapping[str, str] | None = None) -> Path:
    environ = env if env is not None else os.environ
    raw = environ.get("OPS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / "ops").resolve()


def _reject_nested_in_product(destination: Path, product_root: Path) -> None:
    product = product_root.resolve()
    dest = destination.resolve()
    if dest == product:
        raise SiteSyncError(
            f"destination {dest} is the product checkout; a private site dir "
            "must not live inside (or as) the public product tree (ADR 005)"
        )
    try:
        dest.relative_to(product)
    except ValueError:
        return
    raise SiteSyncError(
        f"destination {dest} is nested inside the product checkout {product}; "
        "a private site dir must never live inside a public product working tree (ADR 005)"
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_product_version(product_root: Path | None = None) -> str:
    """Read ``version`` from the product's version.json."""
    root = (product_root or REPO_ROOT).resolve()
    path = root / "version.json"
    if not path.is_file():
        raise SiteSyncError(f"product version.json missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SiteSyncError(f"cannot parse product version.json {path}: {exc}") from exc
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SiteSyncError(f"product version.json missing string 'version' field: {path}")
    return version.strip()


def load_product_commit(product_root: Path | None = None) -> str:
    """Return the full git HEAD SHA of the product checkout."""
    root = (product_root or REPO_ROOT).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SiteSyncError(f"cannot run git rev-parse in product checkout {root}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SiteSyncError(f"cannot determine product_commit (git rev-parse HEAD failed in {root}): {detail}")
    commit = result.stdout.strip()
    if not commit or len(commit) < 7:
        raise SiteSyncError(f"unexpected empty product_commit from git in {root}")
    return commit


def load_manifest(manifest_path: Path | None = None) -> SyncManifest:
    """Load and validate the product sync manifest."""
    path = (manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if not path.is_file():
        raise SiteSyncError(f"sync manifest missing: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SiteSyncError(f"cannot parse sync manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SiteSyncError(f"sync manifest root must be a mapping: {path}")

    contract_version = raw.get("contract_version")
    if contract_version != 1:
        raise SiteSyncError(f"sync manifest contract_version must be 1 (got {contract_version!r}): {path}")
    product = raw.get("product")
    if product != PRODUCT:
        raise SiteSyncError(f"sync manifest product must be {PRODUCT!r} (got {product!r}): {path}")
    files_raw = raw.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        raise SiteSyncError(f"sync manifest must list at least one file under 'files': {path}")

    entries: list[ManifestEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(files_raw):
        if not isinstance(item, dict):
            raise SiteSyncError(f"sync manifest files[{index}] must be a mapping: {path}")
        rel = item.get("path")
        template = item.get("template")
        if not isinstance(rel, str) or not rel.strip():
            raise SiteSyncError(f"sync manifest files[{index}].path must be a non-empty string: {path}")
        if not isinstance(template, str) or not template.strip():
            raise SiteSyncError(f"sync manifest files[{index}].template must be a non-empty string: {path}")
        rel = rel.strip().replace("\\", "/")
        template = template.strip().replace("\\", "/")
        if rel != rel.lstrip("/"):
            raise SiteSyncError(f"sync manifest path must be relative (no leading /): {rel!r}")
        if ".." in Path(rel).parts or ".." in Path(template).parts:
            raise SiteSyncError(f"sync manifest path must not contain '..': {rel!r} / {template!r}")
        if not rel.startswith(GENERATED_PREFIX):
            raise SiteSyncError(f"sync manifest path must be under {GENERATED_PREFIX!r} (got {rel!r}): {path}")
        if rel == LOCKFILE_RELATIVE or rel.endswith("/.lockfile.yml"):
            raise SiteSyncError(f"sync manifest must not list the lockfile itself: {rel!r}")
        if rel in seen:
            raise SiteSyncError(f"sync manifest lists path more than once: {rel!r}")
        seen.add(rel)
        entries.append(ManifestEntry(path=rel, template=template))

    return SyncManifest(contract_version=1, product=PRODUCT, files=tuple(entries))


def resolve_site_dir(
    *,
    dir_path: str | None = None,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Resolve the site directory (explicit dir, STAYTURGID_SITE_DIR, or discovery)."""
    product = (product_root or REPO_ROOT).resolve()
    environ = env if env is not None else os.environ

    if dir_path and str(dir_path).strip():
        destination = Path(dir_path).expanduser()
        if not destination.is_absolute():
            destination = (Path.cwd() / destination).resolve()
        else:
            destination = destination.resolve()
        source = "dir="
    else:
        site_env = environ.get("STAYTURGID_SITE_DIR", "").strip()
        if site_env:
            destination = Path(site_env).expanduser().resolve()
            source = "STAYTURGID_SITE_DIR"
        else:
            destination = _discover_single_site_dir(environ)
            source = "site overlay discovery"

    _reject_nested_in_product(destination, product)

    if not destination.exists():
        raise SiteSyncError(f"site directory does not exist ({source}): {destination}")
    if not destination.is_dir():
        raise SiteSyncError(f"site path is not a directory ({source}): {destination}")

    return destination


def _discover_single_site_dir(environ: Mapping[str, str]) -> Path:
    """Exactly one site-* checkout under OPS_ROOT; zero/multiple → exit 1."""
    ops = _ops_root(environ)
    if not ops.is_dir():
        raise SiteSyncError(f"OPS_ROOT is not a directory: {ops}. Set dir= or STAYTURGID_SITE_DIR explicitly.")
    candidates = sorted(p for p in ops.glob("site-*") if p.is_dir())
    if len(candidates) == 1:
        return candidates[0].resolve()
    if not candidates:
        raise SiteSyncError(
            f"No site overlay found under {ops} (no site-* directory). "
            "Set dir= or STAYTURGID_SITE_DIR to select a site directory."
        )
    listing = ", ".join(str(c) for c in candidates)
    raise SiteSyncError(
        f"Ambiguous site overlay: multiple site-* directories under {ops} ({listing}). "
        "Set dir= or STAYTURGID_SITE_DIR to select one."
    )


def load_lockfile(site_dir: Path) -> dict[str, Any] | None:
    """Load existing lockfile or return None if absent."""
    path = site_dir / LOCKFILE_RELATIVE
    if not path.exists():
        return None
    if not path.is_file():
        raise SiteSyncError(f"lockfile path exists but is not a file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SiteSyncError(f"cannot parse lockfile {path}: {exc}") from exc
    if data is None:
        return None
    if not isinstance(data, dict):
        raise SiteSyncError(f"lockfile root must be a mapping: {path}")
    return data


def lockfile_hashes(lockfile: dict[str, Any] | None) -> dict[str, str]:
    """Map relative path → sha256 from a lockfile document."""
    if not lockfile:
        return {}
    files = lockfile.get("files")
    if files is None:
        return {}
    if not isinstance(files, list):
        raise SiteSyncError("lockfile 'files' must be a list")
    out: dict[str, str] = {}
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise SiteSyncError(f"lockfile files[{index}] must be a mapping")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path.strip():
            raise SiteSyncError(f"lockfile files[{index}].path must be a non-empty string")
        if not isinstance(digest, str) or not digest.strip():
            raise SiteSyncError(f"lockfile files[{index}].sha256 must be a non-empty string")
        out[path.strip()] = digest.strip().lower()
    return out


def _json_string_escape(value: object) -> str:
    """Escape ``value`` for embedding inside an existing double-quoted string
    literal in a rendered fragment (JSON, or a YAML double-quoted scalar —
    JSON's escape set is a strict subset of YAML's double-quoted escapes, so
    this is safe for both). Returns only the escaped content, without the
    surrounding quote characters, so it drops straight into templates that
    already wrap the interpolation in ``"..."``.

    Inventory-controlled values (host.name, host.device_label) are rendered
    into these fragments unescaped otherwise, which lets a crafted host name
    containing a quote inject or corrupt structure in the generated file.
    """
    return json.dumps(str(value))[1:-1]


def _shell_quote(value: object) -> str:
    """POSIX-shell-quote ``value`` for embedding as a single argument inside
    a rendered ``shell:`` block (e.g. OliveTin actions). Inventory-controlled
    values (host.name) are otherwise spliced unquoted into a command line,
    which lets a host name containing shell metacharacters break out of the
    intended single argument.
    """
    return shlex.quote(str(value))


def _render_template(template_path: Path, context: dict[str, Any]) -> bytes:
    environment = Environment(  # nosemgrep
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    environment.filters["json_string_escape"] = _json_string_escape
    environment.filters["shell_quote"] = _shell_quote
    text = template_path.read_text(encoding="utf-8")
    try:
        rendered = environment.from_string(text).render(**context)
    except Exception as exc:  # StrictUndefined (e.g. unregistered port) → loud exit 1
        raise SiteSyncError(f"cannot render sync template {template_path.name!r}: {exc}") from exc
    return rendered.encode("utf-8")


def _assert_rendered_content_parses(entry_path: str, content: bytes) -> None:
    """Defense in depth: a rendered fragment must parse as the format its
    extension promises. Catches template-interpolation bugs (e.g. an
    inventory value that breaks JSON/YAML structure despite escaping) before
    a broken file is written to the committed generated/ area."""
    text = content.decode("utf-8")
    if entry_path.endswith(".json"):
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise SiteSyncError(f"rendered {entry_path!r} is not valid JSON: {exc}") from exc
    elif entry_path.endswith((".yaml", ".yml")):
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SiteSyncError(f"rendered {entry_path!r} is not valid YAML: {exc}") from exc


def _assert_projection_closed_set(entry_path: str, template_path: Path) -> None:
    """Refuse inventory-consuming templates outside the D6 closed write set."""
    if entry_path.startswith(PROJECTION_CLOSED_PREFIXES):
        return
    try:
        text = template_path.read_text(encoding="utf-8")
    except OSError:
        return
    if "inventory_hosts" in text:
        allowed = ", ".join(PROJECTION_CLOSED_PREFIXES)
        raise SiteSyncError(
            f"projection bug (closed write set, design §2): template {template_path.name!r} for "
            f"{entry_path!r} consumes inventory_hosts but renders outside the closed fragment set "
            f"({allowed}). Inventory-derived content is restricted so host edits stay reviewable."
        )


def _collect_inventory_hosts(doc: Any) -> list[dict[str, Any]]:
    """Flatten an Ansible-style inventory document into a list of host dicts.

    The document root maps group names (typically just ``all``) to group
    mappings; each group may carry ``hosts`` and nested ``children`` groups.
    (Pre-D6 this walked only ``children`` keys and returned [] for standard
    ``all:``-rooted inventories — every projection saw zero hosts.)
    """
    out: list[dict[str, Any]] = []

    def _walk_group(group: Any) -> None:
        if not isinstance(group, dict):
            return
        hosts = group.get("hosts")
        if isinstance(hosts, dict):
            for name, vars_raw in hosts.items():
                entry: dict[str, Any] = {"name": str(name)}
                if isinstance(vars_raw, dict):
                    for key, value in vars_raw.items():
                        entry[str(key)] = value
                out.append(entry)
        children = group.get("children")
        if isinstance(children, dict):
            for child in children.values():
                _walk_group(child)

    if isinstance(doc, dict):
        for group in doc.values():
            _walk_group(group)
    return out


def _ports_by_service(ports_doc: dict[str, Any]) -> dict[str, int]:
    """Map service name → port from hosts.* and product_defaults.* entries."""
    result: dict[str, int] = {}

    def _ingest(entries: Any) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            service = entry.get("service")
            port = entry.get("port")
            if isinstance(service, str) and service.strip() and isinstance(port, int):
                result[service.strip()] = port

    hosts = ports_doc.get("hosts")
    if isinstance(hosts, dict):
        for host_data in hosts.values():
            if isinstance(host_data, dict):
                _ingest(host_data.get("ports"))
    product_defaults = ports_doc.get("product_defaults")
    if isinstance(product_defaults, dict):
        for group_entries in product_defaults.values():
            _ingest(group_entries)
    return result


def _site_render_context(
    *,
    site_dir: Path,
    product_root: Path,
    product_version: str,
    product_commit: str,
    source_template: str,
    site_map: SiteMap,
) -> dict[str, Any]:
    """Build template context from product identity + site registry/inventory facts.

    Always includes ``ports`` (service→port mapping) and ``inventory_hosts``
    (sorted host list). Fragments that reference an unregistered port fail via
    StrictUndefined (exit 1).
    """
    context: dict[str, Any] = {
        "product": PRODUCT,
        "product_root": str(product_root.resolve()),
        "stayturgid_root": str(product_root.resolve()),
        "site_dir": str(site_dir.resolve()),
        "product_version": product_version,
        "product_commit": product_commit,
        "source_template": source_template,
        "inventory_path": site_map.relative_path("inventory"),
        "registry_ports_path": site_map.relative_path("registry_ports"),
        "registry_paths_path": site_map.relative_path("registry_paths"),
        "ports": {},
        "inventory_hosts": [],
        # Choice E: empty unless site has caddy_public_hostname (ZO_BASE_URI=/oo).
        "openobserve_http_prefix": "",
    }
    inventory_path = site_map.path("inventory")
    if inventory_path.is_file():
        try:
            inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            inventory = {}
        if isinstance(inventory, dict):
            context["inventory_loaded"] = "true"
            hosts = _collect_inventory_hosts(inventory)
            # Dedupe by name (a host may appear under multiple groups); first wins.
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for host in hosts:
                name = str(host.get("name", ""))
                if not name or name in seen:
                    continue
                seen.add(name)
                unique.append(host)
            unique.sort(key=lambda item: str(item.get("name", "")))
            context["inventory_hosts"] = unique
    # Optional site facts from registry (never required for the minimal scaffold).
    ports_path = site_map.path("registry_ports")
    if ports_path.is_file():
        try:
            ports_doc = yaml.safe_load(ports_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            ports_doc = {}
        if isinstance(ports_doc, dict):
            if isinstance(ports_doc.get("product"), str):
                context["registry_product"] = ports_doc["product"]
            context["ports"] = _ports_by_service(ports_doc)
    paths_path = site_map.path("registry_paths")
    if paths_path.is_file():
        try:
            paths = yaml.safe_load(paths_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            paths = {}
        if isinstance(paths, dict) and isinstance(paths.get("prefixes"), dict):
            # Expose as JSON string for templates that need it later; unused in C3.
            context["registry_has_paths"] = "true"
    # Choice E (D7-ROUTES-E): when the site declares a public front door, own-mode
    # OpenObserve sets ZO_BASE_URI=/oo and remaps API+health under that prefix.
    # Vector sink URIs must match (see stayturgid_sinks.yaml.j2).
    inv_path = site_map.path("inventory")
    group_vars = inv_path.parent / "group_vars" / "all.yml"
    if not group_vars.is_file():
        group_vars = site_dir / "inventory" / "group_vars" / "all.yml"
    if group_vars.is_file():
        try:
            gv = yaml.safe_load(group_vars.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            gv = {}
        if isinstance(gv, dict):
            public_hostname = gv.get("caddy_public_hostname")
            if isinstance(public_hostname, str) and public_hostname.strip():
                context["openobserve_http_prefix"] = "/oo"
    return context


def build_lockfile_document(
    *,
    product_version: str,
    product_commit: str,
    synced: str,
    file_hashes: list[tuple[str, str]],
) -> dict[str, Any]:
    """Assemble the lockfile mapping (stable key order for deterministic dump)."""
    return {
        "contract_version": 1,
        "product": PRODUCT,
        "product_version": product_version,
        "product_commit": product_commit,
        "synced": synced,
        "files": [{"path": path, "sha256": digest} for path, digest in file_hashes],
    }


def dump_lockfile(document: dict[str, Any]) -> bytes:
    """Serialize lockfile YAML with a trailing newline."""
    text = yaml.safe_dump(
        document,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def build_plan(
    *,
    dir_path: str | None = None,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
    force_generated: bool = False,
    manifest_path: Path | None = None,
    product_version: str | None = None,
    product_commit: str | None = None,
    synced: str | None = None,
) -> SyncPlan:
    """Compute the full sync plan without writing anything."""
    product = (product_root or REPO_ROOT).resolve()
    destination = resolve_site_dir(dir_path=dir_path, product_root=product, env=env)
    try:
        site_map = load_site_map(site_dir=destination, product_root=product)
    except SiteMapError as exc:
        raise SiteSyncError(str(exc)) from exc
    manifest = load_manifest(manifest_path)
    version = product_version if product_version is not None else load_product_version(product)
    commit = product_commit if product_commit is not None else load_product_commit(product)
    synced_at = synced if synced is not None else _iso_utc_now()

    existing_lock = load_lockfile(destination)
    known_hashes = lockfile_hashes(existing_lock)

    planned: list[PlannedFile] = []
    new_hashes: list[tuple[str, str]] = []

    for entry in manifest.files:
        template_path = SYNC_TEMPLATE_DIR / entry.template
        if not template_path.is_file():
            raise SiteSyncError(
                f"sync template missing for {entry.path!r}: {template_path} "
                f"(listed in manifest as template={entry.template!r})"
            )
        # Keep templates under sync_templates/ (no path escape).
        try:
            template_path.resolve().relative_to(SYNC_TEMPLATE_DIR.resolve())
        except ValueError as exc:
            raise SiteSyncError(f"sync template escapes sync_templates/: {template_path}") from exc

        _assert_projection_closed_set(entry.path, template_path)
        source_template = f"control/site_contract/sync_templates/{entry.template}"
        context = _site_render_context(
            site_dir=destination,
            product_root=product,
            product_version=version,
            product_commit=commit,
            source_template=source_template,
            site_map=site_map,
        )
        content = _render_template(template_path, context)
        _assert_rendered_content_parses(entry.path, content)
        digest = _sha256_bytes(content)
        new_hashes.append((entry.path, digest))

        target = destination / entry.path
        # Refuse to write outside generated/<product>/ even if manifest is wrong
        # (already validated) — belt-and-suspenders path check.
        _assert_under_generated(destination, target)

        if not target.exists():
            planned.append(
                PlannedFile(
                    relative_path=entry.path,
                    content=content,
                    action="create",
                    sha256=digest,
                )
            )
            continue

        if target.is_dir():
            raise SiteSyncError(f"destination path {target} exists as a directory; expected a file")

        on_disk = target.read_bytes()
        on_disk_hash = _sha256_bytes(on_disk)

        if on_disk == content:
            planned.append(
                PlannedFile(
                    relative_path=entry.path,
                    content=content,
                    action="skip",
                    sha256=digest,
                )
            )
            continue

        lock_hash = known_hashes.get(entry.path)
        if lock_hash is not None and on_disk_hash != lock_hash:
            # Hand-edited generated file (drift).
            if force_generated:
                planned.append(
                    PlannedFile(
                        relative_path=entry.path,
                        content=content,
                        action="overwrite",
                        sha256=digest,
                        drift=False,
                    )
                )
            else:
                planned.append(
                    PlannedFile(
                        relative_path=entry.path,
                        content=content,
                        action="overwrite",
                        sha256=digest,
                        drift=True,
                    )
                )
            continue

        if lock_hash is None and on_disk != content:
            # File present but never locked (or lockfile missing). Treat as drift
            # so the first managed sync does not clobber a hand-placed file silently.
            if force_generated:
                planned.append(
                    PlannedFile(
                        relative_path=entry.path,
                        content=content,
                        action="overwrite",
                        sha256=digest,
                        drift=False,
                    )
                )
            else:
                planned.append(
                    PlannedFile(
                        relative_path=entry.path,
                        content=content,
                        action="overwrite",
                        sha256=digest,
                        drift=True,
                    )
                )
            continue

        # Lock matches on-disk (managed) but product content changed → overwrite.
        planned.append(
            PlannedFile(
                relative_path=entry.path,
                content=content,
                action="overwrite",
                sha256=digest,
            )
        )

    # Deletes: paths in the lockfile that left the product manifest.
    manifest_paths = manifest.paths()
    for locked_path in sorted(known_hashes):
        if locked_path in manifest_paths:
            continue
        if not locked_path.startswith(GENERATED_PREFIX):
            # Corrupt lockfile entry outside generated area — refuse rather than delete.
            raise SiteSyncError(f"lockfile lists path outside {GENERATED_PREFIX!r}: {locked_path!r}")
        target = destination / locked_path
        if target.exists() and target.is_file():
            # Same drift check the overwrite path runs above: a file that
            # left the manifest but was hand-edited since the last sync must
            # not be silently destroyed — refuse (exit 2) unless
            # --force-generated, exactly like acceptance test 3 requires for
            # overwrites.
            on_disk_hash = _sha256_bytes(target.read_bytes())
            lock_hash = known_hashes.get(locked_path)
            drifted = lock_hash is not None and on_disk_hash != lock_hash
            planned.append(
                PlannedFile(
                    relative_path=locked_path,
                    content=None,
                    action="delete",
                    sha256=None,
                    drift=drifted and not force_generated,
                )
            )
        # If already gone, nothing to do (no skip row — not in new manifest).

    content_work = any(item.action != "skip" for item in planned)
    lock_path = destination / LOCKFILE_RELATIVE
    new_hash_map = {path: digest for path, digest in new_hashes}

    # Pure no-op when product identity and file hashes match the existing
    # lockfile and every content file is skip. Do not rewrite `synced` alone —
    # that would defeat idempotent second apply.
    if (
        not content_work
        and existing_lock is not None
        and lock_path.is_file()
        and existing_lock.get("contract_version") == 1
        and existing_lock.get("product") == PRODUCT
        and existing_lock.get("product_version") == version
        and existing_lock.get("product_commit") == commit
        and lockfile_hashes(existing_lock) == new_hash_map
    ):
        lock_bytes = lock_path.read_bytes()
        lock_action: ActionKind = "skip"
        preserved = existing_lock.get("synced")
        if isinstance(preserved, str) and preserved.strip():
            synced_at = preserved.strip()
    else:
        lock_doc = build_lockfile_document(
            product_version=version,
            product_commit=commit,
            synced=synced_at,
            file_hashes=new_hashes,
        )
        lock_bytes = dump_lockfile(lock_doc)
        if lock_path.is_file() and lock_path.read_bytes() == lock_bytes:
            lock_action = "skip"
        elif lock_path.exists():
            lock_action = "overwrite"
        else:
            lock_action = "create"

    return SyncPlan(
        destination=destination,
        product_root=product,
        product_version=version,
        product_commit=commit,
        synced=synced_at,
        files=tuple(planned),
        lockfile_content=lock_bytes,
        lockfile_action=lock_action,
    )


def _plan_olivetin_projection(plan: SyncPlan, *, home: Path | None = None):
    """Plan the OliveTin live-config merge (design §2 single-writer projection).

    Returns an ``olivetin_projection.ProjectionPlan``. Raises SiteSyncError
    (exit 1) for bad action files / missing port, ForeignLiveConfigError
    (exit 2) when the live config is not ours.
    """
    from control.site_contract.olivetin_projection import build_projection

    try:
        site_map = load_site_map(site_dir=plan.destination, product_root=plan.product_root)
    except SiteMapError as exc:
        raise SiteSyncError(str(exc)) from exc
    ports: dict[str, int] = {}
    ports_path = site_map.path("registry_ports")
    if ports_path.is_file():
        try:
            ports_doc = yaml.safe_load(ports_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            ports_doc = {}
        if isinstance(ports_doc, dict):
            ports = _ports_by_service(ports_doc)
    fragment = next(
        (item.content for item in plan.files if item.relative_path == OLIVETIN_FRAGMENT_RELATIVE),
        None,
    )
    return build_projection(
        site_dir=plan.destination,
        site_map=site_map,
        fragment_content=fragment,
        olivetin_port=ports.get("olivetin"),
        product_version=plan.product_version,
        product_commit=plan.product_commit,
        home=home,
        exc=SiteSyncError,
        foreign_exc=ForeignLiveConfigError,
    )


def _assert_under_generated(site_dir: Path, target: Path) -> None:
    generated_root = (site_dir / f"generated/{PRODUCT}").resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(generated_root)
    except ValueError as exc:
        raise SiteSyncError(f"refusing path outside generated/{PRODUCT}/: {target} (resolved {resolved})") from exc


def format_action_list(plan: SyncPlan) -> str:
    """Exact per-file action list for dry-run (includes lockfile)."""
    lines = [f"{item.action:9} {item.relative_path}" for item in plan.files]
    lines.append(f"{plan.lockfile_action:9} {LOCKFILE_RELATIVE}")
    return "\n".join(lines) + ("\n" if lines else "")


def apply_plan(plan: SyncPlan, *, force_generated: bool = False) -> None:
    """Apply planned creates/overwrites/deletes. Refuses on unresolved drift."""
    drifts = plan.drifts
    if drifts and not force_generated:
        paths = ", ".join(item.relative_path for item in drifts)
        raise SiteSyncError(
            f"refusing to modify or delete drifted generated file(s): {paths} "
            "(re-run with --force-generated to overwrite/delete inside generated/ only)",
            exit_code=EXIT_WOULD_OVERWRITE,
        )

    generated_root = plan.destination / f"generated/{PRODUCT}"
    generated_root.mkdir(parents=True, exist_ok=True)

    for item in plan.files:
        target = plan.destination / item.relative_path
        _assert_under_generated(plan.destination, target)
        if item.action == "skip":
            continue
        if item.action == "delete":
            if target.is_file():
                target.unlink()
            continue
        if item.content is None:
            raise SiteSyncError(f"internal error: missing content for {item.relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)

    if plan.lockfile_action != "skip":
        lock_path = plan.destination / LOCKFILE_RELATIVE
        _assert_under_generated(plan.destination, lock_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_bytes(plan.lockfile_content)


def _docs_markdown() -> str:
    """Self-contained Markdown for mode=docs (generic values only)."""
    manifest = load_manifest()
    # Generic RFC-5737-style ports so fragment templates StrictUndefined-render cleanly.
    docs_ports = {
        "landing": 8088,
        "fleet-dashboard": 4097,
        "opencode-web": 4096,
        "ui-tars-vlm": 8081,
        "caddy-health": 8080,
        "vector-otlp-grpc": 4317,
        "vector-otlp-http": 4318,
        "vector-api": 8686,
        "openobserve-http": 5080,
        "grafana": 3000,
        "victoriametrics": 8428,
        "olivetin": 1337,
    }
    # Render each template under generic context to prove StrictUndefined + structure.
    for entry in manifest.files:
        template_path = SYNC_TEMPLATE_DIR / entry.template
        if not template_path.is_file():
            raise SiteSyncError(f"sync template missing: {template_path}")
        context: dict[str, Any] = {
            "product": PRODUCT,
            "product_root": _DOCS_PRODUCT_ROOT,
            "stayturgid_root": _DOCS_PRODUCT_ROOT,
            "site_dir": _DOCS_SITE_DIR,
            "product_version": _DOCS_PRODUCT_VERSION,
            "product_commit": _DOCS_PRODUCT_COMMIT,
            "source_template": f"control/site_contract/sync_templates/{entry.template}",
            "inventory_path": "inventory/hosts.yml",
            "registry_ports_path": "registry/ports.yml",
            "registry_paths_path": "registry/paths.yml",
            "ports": docs_ports,
            "inventory_hosts": [{"name": "example-host", "ansible_host": "192.0.2.10"}],
            "openobserve_http_prefix": "",
        }
        _render_template(template_path, context)

    example_hashes = [
        (
            entry.path,
            "0" * 64,
        )
        for entry in manifest.files
    ]
    example_lock = build_lockfile_document(
        product_version=_DOCS_PRODUCT_VERSION,
        product_commit=_DOCS_PRODUCT_COMMIT,
        synced=_DOCS_SYNCED,
        file_hashes=example_hashes,
    )

    rows: list[tuple[str, str, str]] = []
    for entry in manifest.files:
        note = (
            f"Render `control/site_contract/sync_templates/{entry.template}` with product "
            f"identity from `version.json` + `git rev-parse HEAD`, write to `{entry.path}`, "
            "and record sha256 in the lockfile."
        )
        rows.append((entry.path, "Jinja2 render", note))
    rows.append(
        (
            LOCKFILE_RELATIVE,
            "lockfile write",
            "Write YAML lockfile: contract_version, product, product_version, "
            "product_commit, synced (ISO-8601), and files[].{path,sha256}.",
        )
    )

    lines = [
        "# site-sync — manual equivalent (Site Contract v1)",
        "",
        "This document is produced by `just site-sync mode=docs`. It describes every",
        "filesystem step `site-sync` performs so an operator can reproduce generated",
        "area maintenance by hand. Values below are **generic only** (RFC 5737 /",
        "example inventory names); they are not taken from any private site overlay.",
        "",
        "## Preconditions",
        "",
        f"1. Public product checkout available (example path: `{_DOCS_PRODUCT_ROOT}`).",
        f"2. Existing site directory (example: `{_DOCS_SITE_DIR}`) not nested inside the product tree (ADR 005).",
        "3. Destination resolution: explicit `dir=`, else `STAYTURGID_SITE_DIR`, else",
        "   exactly one `site-*` under `$OPS_ROOT` (default `~/ops`). No hardcoded site name.",
        "4. Product identity: `version.json` → `product_version`; `git rev-parse HEAD` → `product_commit`.",
        "5. Manifest: `control/site_contract/sync_manifest.yml` lists every managed path",
        f"   under `generated/{PRODUCT}/`.",
        "",
        "## CLI",
        "",
        "```text",
        "just site-sync [dir=<path>] [mode=apply|dry-run|docs] [force-generated=1]",
        "```",
        "",
        "- `mode=apply` (default): create/overwrite/delete inside `generated/<product>/` only.",
        "- `mode=dry-run`: print per-file `create` / `overwrite` / `skip` / `delete` actions; no writes.",
        "- `mode=docs`: emit this document; no writes.",
        "- `--force-generated` / `force-generated=1`: overwrite drifted generated files (still only under generated/).",
        "- Exit codes: `0` success/no-op; `1` bad input/precondition; `2` would overwrite drifted content.",
        "- `<site-dir>/site-map.yml` is auto-discovered before defaults. Unknown keys",
        "  fail closed; C4 maps inventory and registries but performs no serverapp writes.",
        "",
        "## Sync rules (spec §4)",
        "",
        "1. Re-render every file in the product manifest from the checked-out product version.",
        "2. Before overwriting, compare on-disk sha256 to the lockfile hash. If they differ",
        "   (hand edit), stop with exit 2 and list drifted paths unless `force-generated`.",
        "3. Paths that leave the product manifest are deleted from the generated area",
        "   (listed in dry-run first).",
        "4. Site facts are read from mapped `inventory`, `registry_ports`, and `registry_paths` locations.",
        "5. Phase C4 never writes outside `generated/<product>/` (no serverapp inject mode).",
        "6. User area outside `generated/<product>/` is never touched.",
        "",
        "## Lockfile shape",
        "",
        "```yaml",
        yaml.safe_dump(example_lock, default_flow_style=False, sort_keys=False).rstrip(),
        "```",
        "",
        "(`sha256` values above are placeholders for documentation only.)",
        "",
        "## Per-file steps (current product manifest)",
        "",
        "| Destination | Action | Manual equivalent |",
        "| --- | --- | --- |",
    ]
    for relative, kind, note in rows:
        safe_note = note.replace("|", "\\|")
        lines.append(f"| `{relative}` | {kind} | {safe_note} |")

    lines.extend(
        [
            "",
            "## Drift recovery",
            "",
            "1. Prefer restoring the generated file from git history of the site repo.",
            "2. Or re-run with `force-generated=1` after reviewing the hand edit.",
            "3. Never hand-edit under `generated/<product>/` going forward.",
            "",
            "## Invariants",
            "",
            f"- Writes only under `generated/{PRODUCT}/` (including `.lockfile.yml`).",
            "- Plan-then-act: dry-run and apply share one action list; exit 2 never partial-writes.",
            "- Second apply with unchanged product content is a no-op (all `skip`).",
            "- Private site data must never nest inside the public product working tree.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_mode(value: str) -> Mode:
    mode = value.strip().lower()
    if mode not in {"apply", "dry-run", "docs"}:
        raise SiteSyncError(f"mode must be apply, dry-run, or docs; got {value!r}")
    return mode  # type: ignore[return-value]


def _parse_bool_flag(value: str | bool | None) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    text = str(value).strip().lower()
    if text in {"", "0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    raise SiteSyncError(f"force-generated must be 0/1 or true/false; got {value!r}")


def run_site_sync(
    *,
    dir_path: str | None = None,
    mode: str = "apply",
    force_generated: bool | str = False,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
    manifest_path: Path | None = None,
    product_version: str | None = None,
    product_commit: str | None = None,
    synced: str | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    home: Path | None = None,
) -> int:
    """Programmatic entry point used by tests and ``main``."""
    out: TextIO = stdout if stdout is not None else sys.stdout
    err: TextIO = stderr if stderr is not None else sys.stderr
    try:
        parsed_mode = _parse_mode(mode)
        force = _parse_bool_flag(force_generated)
        if parsed_mode == "docs":
            print(_docs_markdown(), end="", file=out)
            return EXIT_OK

        plan = build_plan(
            dir_path=dir_path,
            product_root=product_root,
            env=env,
            force_generated=force,
            manifest_path=manifest_path,
            product_version=product_version,
            product_commit=product_commit,
            synced=synced,
        )
        action_list = format_action_list(plan)
        # Planned before any write so a foreign live config (exit 2) or bad
        # action file (exit 1) refuses without partial writes.
        projection = _plan_olivetin_projection(plan, home=home)

        if parsed_mode == "dry-run":
            print(action_list, end="", file=out)
            if projection.action != "noop":
                print(f"{projection.action:9} {projection.live_path} (olivetin projection)", file=out)
            if plan.drifts and not force:
                drift_paths = ", ".join(item.relative_path for item in plan.drifts)
                print(
                    f"error: would modify or delete drifted generated file(s): {drift_paths} "
                    "(re-run with --force-generated to overwrite/delete inside generated/ only)",
                    file=err,
                )
                return EXIT_WOULD_OVERWRITE
            return EXIT_OK

        # apply
        if plan.drifts and not force:
            drift_paths = ", ".join(item.relative_path for item in plan.drifts)
            print(action_list, end="", file=out)
            print(
                f"error: refusing to modify or delete drifted generated file(s): {drift_paths} "
                "(re-run with --force-generated to overwrite/delete inside generated/ only)",
                file=err,
            )
            return EXIT_WOULD_OVERWRITE

        apply_plan(plan, force_generated=force)
        if projection.action == "overwrite":
            from control.site_contract.olivetin_projection import apply_projection

            apply_projection(projection)
            print(f"site-sync: olivetin projection: overwrite {projection.live_path}", file=err)
        elif projection.action == "skip":
            print(f"site-sync: olivetin projection: skip {projection.live_path} (up to date)", file=err)
        created = sum(1 for item in plan.files if item.action == "create")
        overwritten = sum(1 for item in plan.files if item.action == "overwrite")
        skipped = sum(1 for item in plan.files if item.action == "skip")
        deleted = sum(1 for item in plan.files if item.action == "delete")
        print(
            f"site-sync: {plan.destination} "
            f"(created={created}, overwritten={overwritten}, skipped={skipped}, "
            f"deleted={deleted}, lockfile={plan.lockfile_action}, "
            f"product_version={plan.product_version}, product_commit={plan.product_commit[:12]})",
            file=err,
        )
        return EXIT_OK
    except SiteSyncError as exc:
        print(f"error: {exc}", file=err)
        return exc.exit_code
    except OSError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_PRECONDITION


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync product-owned generated files into a stayturgid site overlay (Site Contract v1).",
    )
    parser.add_argument("--dir", dest="dir_path", default="", help="explicit site directory")
    parser.add_argument(
        "--mode",
        default="apply",
        help="apply (default), dry-run, or docs",
    )
    parser.add_argument(
        "--force-generated",
        action="store_true",
        default=False,
        help="overwrite drifted files inside generated/<product>/ only",
    )
    parser.add_argument(
        "assignments",
        nargs="*",
        help="optional KEY=VALUE assignments: dir=, mode=, force-generated=",
    )
    return parser


def _merge_assignments(
    *,
    dir_path: str,
    mode: str,
    force_generated: bool,
    assignments: Sequence[str],
) -> tuple[str, str, bool]:
    """Merge KEY=VALUE tokens (from the just wrapper) into flag values."""
    allowed = {"dir", "mode", "force-generated"}
    values: dict[str, str] = {
        "dir": dir_path,
        "mode": mode,
        "force-generated": "1" if force_generated else "0",
    }
    for token in assignments:
        if "=" not in token:
            raise SiteSyncError(
                f"unknown argument {token!r}; expected dir= / mode= / force-generated= or the matching --flag forms"
            )
        key, value = token.split("=", 1)
        if key not in allowed:
            raise SiteSyncError(f"unknown assignment {key!r}; expected one of: {', '.join(sorted(allowed))}")
        values[key] = value
    return values["dir"], values["mode"], _parse_bool_flag(values["force-generated"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        dir_path, mode, force = _merge_assignments(
            dir_path=args.dir_path,
            mode=args.mode,
            force_generated=args.force_generated,
            assignments=args.assignments,
        )
    except SiteSyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    return run_site_sync(
        dir_path=dir_path or None,
        mode=mode,
        force_generated=force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
