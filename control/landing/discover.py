#!/usr/bin/env python3
"""Network service discovery — scans local and Tailscale hosts for HTTP servers.

Updates user-local landing state with reachability and last-seen timestamps.
Designed to run periodically (via launchd or cron). Never removes entries —
unreachable services stay in the catalog with reachable=false.
"""

from __future__ import annotations

import datetime
import os
import socket
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_LIB = _REPO / "control" / "lib"
sys.path.insert(0, str(_REPO))

from control.landing import state
from control.lib.site_discovery import (
    SiteDiscoveryError,
    SiteSelection,
    announce_site_selection,
    ensure_private_companion,
    reject_private_companion_overlay,
    resolve_site_selection,
)

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional for bare runs
    yaml = None

SERVICES_FILE = state.STATE_FILE

# ── Known service definitions (URL, label, group) ───────────────────────────
KNOWN_SERVICES: list[dict] = [
    # Mac control node — all served via Caddy HTTPS (Choice E paths)
    {"url": "https://mac.example.ts.net", "label": "Network Landing (root)", "group": "mac"},
    {"url": "https://mac.example.ts.net/grafana/", "label": "Grafana (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/oo/", "label": "OpenObserve (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/olivetin/", "label": "OliveTin (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/vm/", "label": "VictoriaMetrics (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/opencode/", "label": "OpenCode Web (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/dashboard/", "label": "Fleet Dashboard (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/stats/", "label": "Fleet Stats (HTTPS)", "group": "mac"},
    # Localhost (direct, for Mac-only access)
    {"url": "http://localhost:4096", "label": "OpenCode (localhost)", "group": "mac"},
    {"url": "http://localhost:4097", "label": "Dashboard (localhost)", "group": "mac"},
    {"url": "http://localhost:4097/stats", "label": "Stats (localhost)", "group": "mac"},
    {"url": "http://localhost:3000", "label": "Grafana (localhost)", "group": "mac"},
    {"url": "http://localhost:5080/oo/", "label": "OpenObserve (localhost)", "group": "mac"},
    {"url": "http://localhost:1337", "label": "OliveTin (localhost)", "group": "mac"},
    {"url": "http://localhost:8428", "label": "VictoriaMetrics (localhost)", "group": "mac"},
    {"url": "http://localhost:8088", "label": "Network Landing (localhost)", "group": "mac"},
    {"url": "http://localhost:8080", "label": "Caddy Health", "group": "mac"},
    # mDNS (Bonjour, LAN-only) — use if macOS hostname differs
    # Devices — Tailscale IPs
    {"url": "http://100.0.0.11:65000", "label": "oneui-device FIRERPA", "group": "devices"},
    {"url": "http://100.0.0.12:65000", "label": "stock-android-device FIRERPA", "group": "devices"},
    {"url": "http://100.0.0.13:65000", "label": "fireos-device FIRERPA", "group": "devices"},
    # Devices — LAN
    {"url": "http://192.0.2.11:65000", "label": "oneui-device FIRERPA (LAN)", "group": "devices"},
    {"url": "http://192.0.2.12:65000", "label": "stock-android-device FIRERPA (LAN)", "group": "devices"},
    # Devices — MagicDNS
    {"url": "http://oneui-device.example.ts.net:65000", "label": "oneui-device FIRERPA (MagicDNS)", "group": "devices"},
    {
        "url": "http://stock-android-device.example.ts.net:65000",
        "label": "stock-android-device FIRERPA (MagicDNS)",
        "group": "devices",
    },
    {
        "url": "http://fireos-device.example.ts.net:65000",
        "label": "fireos-device FIRERPA (MagicDNS)",
        "group": "devices",
    },
    # Additional Mac services discovered dynamically
    {"url": "http://localhost:9000", "label": "PHP-FPM / Dev Server", "group": "mac"},
]

# The committed catalog is the source of truth; the fallback list keeps older
# checkouts importable until their catalog has been migrated.
KNOWN_SERVICES = state.load_catalog().get("services", KNOWN_SERVICES)

# Generic catalog host in services.json / KNOWN_SERVICES (RFC-style example).
_CATALOG_PUBLIC_HOST = "mac.example.ts.net"


def _resolve_site(environ: Mapping[str, str]) -> SiteSelection:
    """Resolve the landing command's site using the product-wide precedence."""

    ensure_private_companion(environ)
    explicit_config = environ.get("ANSIBLE_CONFIG", "").strip()
    explicit_site = environ.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit_config:
        config = Path(explicit_config).expanduser()
        if not config.is_absolute():
            config = (Path.cwd() / config).resolve()
        if not config.is_file():
            raise SiteDiscoveryError(f"ANSIBLE_CONFIG points to a missing file: {config}")
        selection = SiteSelection(path=config.parent.resolve(), source="ANSIBLE_CONFIG")
    elif explicit_site:
        selection = SiteSelection(
            path=Path(explicit_site).expanduser().resolve(),
            source="STAYTURGID_SITE_DIR",
        )
    else:
        selection = resolve_site_selection(environ)
    reject_private_companion_overlay(selection.path, environ)
    if not selection.path.is_dir():
        raise SiteDiscoveryError(
            f"Selected site directory does not exist or is not a directory ({selection.source}): {selection.path}"
        )
    return selection


def _site_caddy_public_hostname(site_dir: Path) -> str | None:
    """Read caddy_public_hostname from site inventory group_vars if present."""
    candidates = [site_dir / "inventory" / "group_vars" / "all.yml"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if yaml is not None:
            try:
                data = yaml.safe_load(text) or {}
            except yaml.YAMLError:
                data = {}
            if isinstance(data, dict):
                value = data.get("caddy_public_hostname")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        # Fallback without PyYAML (bare python3 on operator Macs).
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "caddy_public_hostname" not in stripped:
                continue
            if ":" not in stripped:
                continue
            key, _, rest = stripped.partition(":")
            if key.strip() != "caddy_public_hostname":
                continue
            value = rest.strip().strip("\"'")
            if value:
                return value
    return None


def _known_services_for_site(site_dir: Path) -> list[dict]:
    """Catalog services with example.ts.net rewritten to the site front-door host."""
    host = _site_caddy_public_hostname(site_dir)
    if not host:
        return list(KNOWN_SERVICES)
    out: list[dict] = []
    for entry in KNOWN_SERVICES:
        item = dict(entry)
        url = str(item.get("url") or "")
        if _CATALOG_PUBLIC_HOST in url:
            item["url"] = url.replace(_CATALOG_PUBLIC_HOST, host)
        out.append(item)
    return out


def _http_probe(url: str, timeout: float = 3.0) -> int | None:
    """Return HTTP status code or None if unreachable."""
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", str(int(timeout)), url],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        code = r.stdout.strip()
        return int(code) if code.isdigit() and code != "000" else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_registry_ports_path(site_dir: Path) -> Path | None:
    """Locate ``registry/ports.yml`` under the selected site overlay."""

    candidate = site_dir / "registry" / "ports.yml"
    return candidate if candidate.is_file() else None


PROCESS_SERVICE_NAMES: dict[str, str] = {
    "ollama": "Ollama LLM API",
    "opencode": "OpenCode Web",
    "caddy": "Caddy Web Server",
    "vector": "Vector Collector",
    "openobserve": "OpenObserve",
    "grafana": "Grafana",
    "victoria-metrics": "VictoriaMetrics",
    "OliveTin": "OliveTin",
    "Dropbox": "Dropbox Helper",
    "PhotoSync": "PhotoSync Companion",
    "blackbox_exporter": "Blackbox Exporter",
    "blackbox_": "Blackbox Exporter",
    "adb": "ADB Server",
    "agy": "Antigravity CLI (agy)",
    "Raycast": "Raycast Helper",
    "ARDAgent": "Apple Remote Desktop",
    "logioption": "Logi Options+ Daemon",
    "logioptio": "Logi Options+ Daemon",
    "zed": "Zed Editor Helper",
    "omlx": "omlx Local MLX Server",
}


def _format_service_label(name: str) -> str:
    """Format kebab-case or snake_case registry service names into title-cased labels."""
    replacements = {
        "litellm-proxy": "LiteLLM Proxy",
        "vector-otlp-grpc": "Vector OTLP gRPC",
        "vector-otlp-http": "Vector OTLP HTTP",
        "vector-api": "Vector API",
        "ollama-llm-api": "Ollama LLM API",
        "blackbox-exporter": "Blackbox Exporter",
        "antigravity-agy-ipc": "Antigravity CLI (agy) IPC",
        "antigravity-agy-sidecar": "Antigravity CLI (agy) Sidecar",
        "caddy-http-redirect": "Caddy HTTP Redirect",
        "caddy-https": "Caddy HTTPS Front Door",
        "caddy-health": "Caddy Health",
        "opencode-web": "OpenCode Web",
        "fleet-dashboard": "Fleet Dashboard",
        "adb-server": "ADB Server",
        "openobserve-http": "OpenObserve HTTP",
        "openobserve-grpc": "OpenObserve gRPC",
        "victoriametrics": "VictoriaMetrics",
        "olivetin": "OliveTin",
        "dropbox-lansync": "Dropbox LAN Sync",
        "dropbox-local-helper": "Dropbox Local Helper",
        "dropbox-local-api": "Dropbox Local API",
        "raycast-helper": "Raycast Helper",
        "zed-editor-helper": "Zed Editor Helper",
        "logi-options-daemon": "Logi Options+ Daemon",
        "apple-remote-desktop": "Apple Remote Desktop",
        "macos-screen-sharing": "macOS Screen Sharing",
        "photosync": "PhotoSync Companion",
        "omlx": "omlx Local MLX Server",
    }
    if name in replacements:
        return replacements[name]
    return name.replace("-", " ").replace("_", " ").title()


def _parse_ports_yaml_fallback(path: Path) -> dict[int, str]:
    res: dict[int, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return res
    import re

    port_re = re.compile(r"port:\s*(\d+)")
    svc_re = re.compile(r"service:\s*([a-zA-Z0-9_-]+)")
    for line in lines:
        line = line.strip()
        if line.startswith("#") or "port:" not in line:
            continue
        pm = port_re.search(line)
        sm = svc_re.search(line)
        if pm:
            p = int(pm.group(1))
            svc = sm.group(1) if sm else f"Port {p}"
            res[p] = svc
    return res


def load_registered_ports(
    registry_path: Path | None = None,
    *,
    site_dir: Path | None = None,
    return_map: bool = False,
) -> set[int] | dict[int, str]:
    """Return the set or dict (port -> service) of ports declared in the site registry (any host)."""
    path = registry_path
    if path is None:
        if site_dir is None:
            selection = _resolve_site(os.environ)
            announce_site_selection(selection, command="landing-discover")
            site_dir = selection.path
        path = _resolve_registry_ports_path(site_dir)
    if path is None or not path.is_file():
        return {} if return_map else set()
    if yaml is None:
        fallback_map = _parse_ports_yaml_fallback(path)
        return fallback_map if return_map else set(fallback_map.keys())
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {} if return_map else set()

    ports_set: set[int] = set()
    ports_map: dict[int, str] = {}

    def _ingest(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("port"), int):
                p = entry["port"]
                svc = str(entry.get("service") or f"Port {p}")
                ports_set.add(p)
                ports_map[p] = svc

    hosts = doc.get("hosts") if isinstance(doc, dict) else None
    if isinstance(hosts, dict):
        for host_data in hosts.values():
            if isinstance(host_data, dict):
                _ingest(host_data.get("ports"))
    product_defaults = doc.get("product_defaults") if isinstance(doc, dict) else None
    if isinstance(product_defaults, dict):
        for group_entries in product_defaults.values():
            _ingest(group_entries)

    return ports_map if return_map else ports_set


def _scan_localhost(*, registered_ports: set[int] | dict[int, str] | None = None) -> list[dict]:
    """Scan the Mac's local ports for HTTP servers using lsof.

    When *registered_ports* is provided, listeners not listed in the site
    registry are badged ``unregistered`` (Phase D4 registry drift check).
    """
    services: list[dict] = []
    try:
        r = subprocess.run(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return services

    reg_set: set[int] = set()
    reg_map: dict[int, str] = {}
    if isinstance(registered_ports, dict):
        reg_map = registered_ports
        reg_set = set(registered_ports.keys())
    elif isinstance(registered_ports, set):
        reg_set = registered_ports

    scanned: set[int] = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 9 or "LISTEN" not in line:
            continue
        proc_cmd = parts[0]
        addr = parts[8]
        if ":" not in addr:
            continue
        try:
            port = int(addr.rsplit(":", 1)[-1])
        except ValueError:
            continue
        if port in scanned or port < 1 or port > 65535:
            continue
        scanned.add(port)

        status = _http_probe(f"http://127.0.0.1:{port}", timeout=2.0)
        if status is not None:
            unregistered = registered_ports is not None and port not in reg_set

            # Resolve descriptive service label
            if port in reg_map and reg_map[port] and not reg_map[port].startswith("TODO"):
                base_label = _format_service_label(reg_map[port])
            elif proc_cmd in PROCESS_SERVICE_NAMES:
                base_label = PROCESS_SERVICE_NAMES[proc_cmd]
            else:
                base_label = f"Port {port}"

            label = base_label + (" [unregistered]" if unregistered else "")
            note = f"HTTP {status}"
            if unregistered:
                note += "; not in registry/ports.yml"
            entry: dict[str, Any] = {
                "url": f"http://localhost:{port}",
                "label": label,
                "group": "mac",
                "note": note,
            }
            if unregistered:
                entry["unregistered"] = True
            services.append(entry)

    return services


def discover(environ: Mapping[str, str] | None = None) -> dict:
    """Run a full discovery scan. Returns the updated catalog."""
    env = os.environ if environ is None else environ
    selection = _resolve_site(env)
    announce_site_selection(selection, command="landing-discover")
    site_dir = selection.path
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing: dict = state.load_state()

    # Start with known services, merge with existing
    known_urls: dict[str, dict] = {}
    for s in existing.get("services", []):
        known_urls[s["url"]] = s

    # Purge un-rewritten catalog placeholder URLs (e.g., mac.example.ts.net) when a real site host exists
    public_host = _site_caddy_public_hostname(site_dir)
    if public_host:
        for url_key in list(known_urls.keys()):
            if _CATALOG_PUBLIC_HOST in url_key or ".example.ts.net" in url_key:
                del known_urls[url_key]

    # Add/update known services (site MagicDNS substituted for catalog placeholder)
    for s in _known_services_for_site(site_dir):
        url = s["url"]
        if url in known_urls:
            known_urls[url].update({k: v for k, v in s.items() if k != "url"})
        else:
            known_urls[url] = dict(s)

    # Discover new http ports on localhost; badge registry drift (D4).
    registered = load_registered_ports(site_dir=site_dir, return_map=True)
    for s in _scan_localhost(registered_ports=registered if registered else None):
        url = s["url"]
        if url not in known_urls:
            known_urls[url] = s
        else:
            # Refresh label and unregistered badge status on existing entries
            known_urls[url]["label"] = s["label"]
            if s.get("unregistered"):
                known_urls[url]["unregistered"] = True
            elif "unregistered" in known_urls[url]:
                del known_urls[url]["unregistered"]

    # Probe reachability
    hidden = set(existing.get("hidden", []))
    services: list[dict] = []
    static_urls = {ks["url"] for ks in _known_services_for_site(site_dir)}
    for url, s in sorted(known_urls.items()):
        s["url"] = url
        status = _http_probe(url)
        if status is not None:
            s["reachable"] = True
            s["last_seen"] = now
            s["status_code"] = status
            if url not in hidden:
                services.append(s)
        else:
            s["reachable"] = False
            # Check if this is an auto-discovered unregistered port that is no longer reachable.
            # Dynamic localhost entries (e.g., ephemeral ports) that are no longer listening are pruned.
            try:
                port = int(url.rsplit(":", 1)[-1]) if ":" in url else None
            except ValueError:
                port = None
            is_registered_port = registered is not None and port is not None and port in registered
            is_static = url in static_urls or is_registered_port

            if not is_static and (s.get("unregistered") or url.startswith("http://localhost:")):
                # Prune unreachable dynamic/ephemeral ports
                continue

            if s.get("last_seen") is None:
                # Might just be down temporarily; also try TCP
                host = url.split("://")[1].split(":")[0]
                if port is None:
                    port = 80
                if _tcp_probe(host, port):
                    s["reachable"] = False

            if url not in hidden:
                services.append(s)

    output = {
        "services": services,
        "hidden": sorted(hidden),
        "last_scan": now,
    }
    try:
        state.write_state(output)
    except OSError:
        pass

    return output


if __name__ == "__main__":
    try:
        result = discover()
    except SiteDiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    reachable = sum(1 for s in result["services"] if s.get("reachable"))
    total = len(result["services"])
    unregistered = sum(1 for s in result["services"] if s.get("unregistered"))
    print(f"Discovery complete: {reachable}/{total} services reachable")
    if unregistered:
        print(f"Registry drift: {unregistered} unregistered listener(s) (not in registry/ports.yml)")
    for s in result["services"]:
        status = "✓" if s.get("reachable") else "✗"
        badge = " [unregistered]" if s.get("unregistered") else ""
        print(f"  {status} {s['url']:50s} — {s['label']}{badge if badge not in s.get('label', '') else ''}")
