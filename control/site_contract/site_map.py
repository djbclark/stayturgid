"""Load and validate Site Contract v1 ``site-map.yml`` files.

Phase C4 consumes only contract paths used by ``site-init`` and ``site-sync``.
Serverapp mappings are validated and retained for Phase D, but never acted on
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "error: PyYAML is required for site-map.yml support "
        "(install ansible-core, or use the project test venv: just test-venv)"
    ) from exc

MAP_FILENAME = "site-map.yml"
PRODUCT = "stayturgid"

DEFAULT_PATHS = {
    "inventory": "inventory/hosts.yml",
    "registry_ports": "registry/ports.yml",
    "registry_paths": "registry/paths.yml",
}
ALLOWED_TOP_LEVEL_KEYS = frozenset({"contract_version", "paths", "serverapps"})
ALLOWED_PATH_KEYS = frozenset(DEFAULT_PATHS)
ALLOWED_SERVERAPPS = frozenset(
    {
        "caddy",
        "vector",
        "openobserve",
        "victoriametrics",
        "grafana",
        "olivetin",
        "landing",
    }
)
ALLOWED_SERVERAPP_KEYS = frozenset({"config", "fragment_dir", "mode"})
ALLOWED_SERVERAPP_MODES = frozenset({"own", "inject", "off"})


class SiteMapError(Exception):
    """Invalid or unsafe ``site-map.yml`` input."""


@dataclass(frozen=True)
class ServerAppMap:
    """Validated Phase D serverapp mapping (not acted on in C4)."""

    config: Path | None = None
    fragment_dir: Path | None = None
    mode: str | None = None


@dataclass(frozen=True)
class SiteMap:
    """Resolved Site Contract v1 mapping for one site directory."""

    site_dir: Path
    source: Path | None
    paths: dict[str, Path]
    serverapps: dict[str, ServerAppMap] = field(default_factory=dict)

    def path(self, key: str) -> Path:
        return self.paths[key]

    def relative_path(self, key: str) -> str:
        return self.path(key).relative_to(self.site_dir).as_posix()


def _unknown_keys(raw: dict[Any, Any], allowed: frozenset[str], location: str) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise SiteMapError(f"unknown {location} key(s): {', '.join(unknown)}")


def _resolve_contract_path(*, key: str, value: Any, site_dir: Path, product_root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SiteMapError(f"paths.{key} must be a non-empty path string")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = site_dir / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(site_dir)
    except ValueError as exc:
        raise SiteMapError(
            f"paths.{key} escapes the site directory {site_dir}: {value!r} resolves to {resolved}"
        ) from exc
    generated_root = (site_dir / "generated" / PRODUCT).resolve()
    try:
        resolved.relative_to(generated_root)
    except ValueError:
        pass
    else:
        raise SiteMapError(f"paths.{key} resolves inside site-sync's owned generated/{PRODUCT}/ area: {resolved}")
    try:
        resolved.relative_to(product_root)
    except ValueError:
        pass
    else:
        raise SiteMapError(
            f"paths.{key} resolves inside the public product checkout {product_root} (ADR 005): {resolved}"
        )
    return resolved


def _resolve_serverapp_path(*, app: str, key: str, value: Any, site_dir: Path, product_root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SiteMapError(f"serverapps.{app}.{key} must be a non-empty path string")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = site_dir / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(product_root)
    except ValueError:
        return resolved
    raise SiteMapError(
        f"serverapps.{app}.{key} resolves inside the public product checkout {product_root} (ADR 005): {resolved}"
    )


def _parse_serverapps(
    raw: Any,
    *,
    site_dir: Path,
    product_root: Path,
) -> dict[str, ServerAppMap]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SiteMapError("serverapps must be a mapping")
    _unknown_keys(raw, ALLOWED_SERVERAPPS, "serverapps")
    parsed: dict[str, ServerAppMap] = {}
    for app, app_raw in raw.items():
        if not isinstance(app_raw, dict):
            raise SiteMapError(f"serverapps.{app} must be a mapping")
        _unknown_keys(app_raw, ALLOWED_SERVERAPP_KEYS, f"serverapps.{app}")
        config = None
        fragment_dir = None
        mode = app_raw.get("mode")
        if "config" in app_raw:
            config = _resolve_serverapp_path(
                app=app,
                key="config",
                value=app_raw["config"],
                site_dir=site_dir,
                product_root=product_root,
            )
        if "fragment_dir" in app_raw:
            fragment_dir = _resolve_serverapp_path(
                app=app,
                key="fragment_dir",
                value=app_raw["fragment_dir"],
                site_dir=site_dir,
                product_root=product_root,
            )
        if mode is not None:
            # YAML 1.1 loads bare `off`/`on` as booleans; accept that spelling.
            if mode is False:
                mode = "off"
            elif mode is True:
                raise SiteMapError(
                    f"serverapps.{app}.mode: bare YAML true/on is ambiguous; use quoted 'own', 'inject', or 'off'"
                )
            if not isinstance(mode, str) or mode not in ALLOWED_SERVERAPP_MODES:
                allowed = ", ".join(sorted(ALLOWED_SERVERAPP_MODES))
                raise SiteMapError(f"serverapps.{app}.mode must be one of: {allowed}; got {mode!r}")
        parsed[app] = ServerAppMap(config=config, fragment_dir=fragment_dir, mode=mode)
    return parsed


def load_site_map(
    *,
    site_dir: Path,
    product_root: Path,
    map_path: str | Path | None = None,
) -> SiteMap:
    """Load an explicit map or auto-discover ``site-map.yml`` at the site root."""
    site = site_dir.resolve()
    product = product_root.resolve()
    if map_path is not None and str(map_path).strip():
        source = Path(map_path).expanduser()
        if not source.is_absolute():
            source = (Path.cwd() / source).resolve()
        else:
            source = source.resolve()
        if not source.is_file():
            raise SiteMapError(f"site map does not exist or is not a file: {source}")
    else:
        candidate = site / MAP_FILENAME
        source = candidate if candidate.is_file() else None

    defaults = {
        key: _resolve_contract_path(
            key=key,
            value=value,
            site_dir=site,
            product_root=product,
        )
        for key, value in DEFAULT_PATHS.items()
    }
    if source is None:
        return SiteMap(site_dir=site, source=None, paths=defaults)

    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SiteMapError(f"cannot parse site map {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SiteMapError(f"site map root must be a mapping: {source}")
    _unknown_keys(raw, ALLOWED_TOP_LEVEL_KEYS, "top-level")
    version = raw.get("contract_version")
    if type(version) is not int or version != 1:
        raise SiteMapError(f"contract_version must be integer 1 (got {version!r}): {source}")

    paths_raw = raw.get("paths", {})
    if paths_raw is None:
        paths_raw = {}
    if not isinstance(paths_raw, dict):
        raise SiteMapError("paths must be a mapping")
    _unknown_keys(paths_raw, ALLOWED_PATH_KEYS, "paths")
    paths = dict(defaults)
    for key, value in paths_raw.items():
        paths[key] = _resolve_contract_path(
            key=key,
            value=value,
            site_dir=site,
            product_root=product,
        )
    duplicates: dict[Path, list[str]] = {}
    for key, value in paths.items():
        duplicates.setdefault(value, []).append(key)
    collisions = [keys for keys in duplicates.values() if len(keys) > 1]
    if collisions:
        names = "; ".join(", ".join(keys) for keys in collisions)
        raise SiteMapError(f"contract paths must resolve to distinct files; collision: {names}")

    serverapps = _parse_serverapps(
        raw.get("serverapps"),
        site_dir=site,
        product_root=product,
    )
    return SiteMap(site_dir=site, source=source, paths=paths, serverapps=serverapps)
