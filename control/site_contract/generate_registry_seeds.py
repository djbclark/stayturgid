#!/usr/bin/env python3
"""Generate site registry seeds from product-owned defaults and declarations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = Path(__file__).resolve().parent
SOURCE_MAP = CONTRACT_DIR / "registry_sources.yml"
TEMPLATE_DIR = CONTRACT_DIR / "templates" / "registry"

_HOME_LOOKUP = re.compile(r"\{\{\s*lookup\('env',\s*'HOME'\)\s*\}\}")
_JINJA_DEFAULT_INTEGER = re.compile(r"default\(\s*(\d+)\s*(?:,\s*true\s*)?\)")


class RegistrySourceError(ValueError):
    """Raised when a declared product claim cannot be resolved."""


class _IndentedSafeDumper(yaml.SafeDumper):
    """Match the repository's yamllint indentation for block sequences."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def _source_label(source: dict[str, object]) -> str:
    selector = source.get("yaml_path") or source.get("json_service_label") or "regex"
    return f"{source['file']}#{selector}"


def _nested_value(data: object, dotted_path: str) -> object:
    value = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise RegistrySourceError(f"missing YAML path {dotted_path!r}")
        value = value[part]
    return value


def _load_source_value(source: dict[str, object]) -> object:
    path = REPO_ROOT / str(source["file"])
    if "yaml_path" in source:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        value = _nested_value(data, str(source["yaml_path"]))
    elif "json_service_label" in source:
        data = json.loads(path.read_text(encoding="utf-8"))
        label = source["json_service_label"]
        matches = [item for item in data["services"] if item.get("label") == label]
        if len(matches) != 1:
            raise RegistrySourceError(f"expected one service labelled {label!r} in {path}")
        parsed = urlparse(matches[0]["url"])
        value = parsed.port
    elif "regex" in source:
        matches = re.findall(str(source["regex"]), path.read_text(encoding="utf-8"), re.MULTILINE)
        if len(matches) != 1:
            raise RegistrySourceError(f"expected one regex match in {path}, found {len(matches)}")
        value = matches[0]
    else:
        raise RegistrySourceError(f"source has no supported selector: {source}")

    if source.get("extract") == "jinja_default_integer":
        defaults = _JINJA_DEFAULT_INTEGER.findall(str(value))
        if len(defaults) != 1:
            raise RegistrySourceError(f"expected one integer Jinja default in {_source_label(source)}")
        value = defaults[0]
    return value


def _port_from_source(source: dict[str, object]) -> int:
    value = _load_source_value(source)
    if isinstance(value, bool):
        raise RegistrySourceError(f"port source {_source_label(source)} resolved to a boolean")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise RegistrySourceError(f"port source {_source_label(source)} is not an integer: {value!r}") from exc
    if not 1 <= port <= 65535:
        raise RegistrySourceError(f"port source {_source_label(source)} is out of range: {port}")
    return port


def _path_from_source(source: dict[str, object], suffix: str = "") -> str:
    value = _load_source_value(source)
    if not isinstance(value, str):
        raise RegistrySourceError(f"path source {_source_label(source)} is not text: {value!r}")
    value = _HOME_LOOKUP.sub("~", value)
    if "{{" in value or "}}" in value:
        raise RegistrySourceError(f"path source {_source_label(source)} needs unsupported Jinja resolution")
    return value.rstrip("/") + suffix


def load_source_map() -> dict[str, list[dict[str, object]]]:
    """Load and minimally validate the allocation-free source manifest."""
    data = yaml.safe_load(SOURCE_MAP.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("ports"), list) or not isinstance(data.get("paths"), list):
        raise RegistrySourceError("registry_sources.yml must contain ports and paths lists")
    return data


def port_registry() -> dict[str, object]:
    """Resolve the product port claims, grouped without inventing site hosts."""
    claims: dict[str, list[dict[str, object]]] = {}
    for spec in load_source_map()["ports"]:
        source = spec["source"]
        assert isinstance(source, dict)
        scope = str(spec["scope"])
        claims.setdefault(scope, []).append(
            {
                "port": _port_from_source(source),
                "bind": spec["bind"],
                "owner": "stayturgid",
                "service": spec["service"],
                "status": "default-claim",
                "source": _source_label(source),
            }
        )
    for entries in claims.values():
        entries.sort(key=lambda entry: (int(entry["port"]), str(entry["service"])))
    return {"contract_version": 1, "product": "stayturgid", "hosts": {}, "product_defaults": claims}


def path_registry() -> dict[str, object]:
    """Resolve product-owned prefixes while retaining derivation metadata."""
    prefixes: list[str] = []
    sources: dict[str, dict[str, str]] = {}
    for spec in load_source_map()["paths"]:
        source = spec["source"]
        assert isinstance(source, dict)
        path = _path_from_source(source, str(spec.get("suffix", "")))
        if path not in prefixes:
            prefixes.append(path)
        metadata = {"source": _source_label(source)}
        if "access" in spec:
            metadata["access"] = str(spec["access"])
        sources[path] = metadata
    return {
        "contract_version": 1,
        "product": "stayturgid",
        "prefixes": {"stayturgid": prefixes},
        "claim_sources": sources,
    }


def _dump_seed(kind: str, data: dict[str, object]) -> str:
    header = (
        "---\n"
        f"# Product-owned {kind} defaults for a new site registry.\n"
        "# Generated by control/site_contract/generate_registry_seeds.py; do not hand-copy values.\n"
        "# Site inventory may override these defaults and remains authoritative.\n"
    )
    return header + yaml.dump(
        data,
        Dumper=_IndentedSafeDumper,
        sort_keys=False,
        explicit_start=False,
        width=120,
    )


def rendered_seeds() -> dict[str, str]:
    """Return the reproducible registry template payloads."""
    return {"ports.yml": _dump_seed("port", port_registry()), "paths.yml": _dump_seed("path", path_registry())}


def write_seeds() -> None:
    """Write both committed registry templates."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in rendered_seeds().items():
        (TEMPLATE_DIR / name).write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed registry templates are stale")
    args = parser.parse_args()
    expected = rendered_seeds()
    if args.check:
        stale = [
            name for name, content in expected.items() if (TEMPLATE_DIR / name).read_text(encoding="utf-8") != content
        ]
        if stale:
            parser.error(f"stale registry templates: {', '.join(stale)}")
        return 0
    write_seeds()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
