#!/usr/bin/env python3
"""Network service discovery — scans local and Tailscale hosts for HTTP servers.

Updates user-local landing state with reachability and last-seen timestamps.
Designed to run periodically (via launchd or cron). Never removes entries —
unreachable services stay in the catalog with reachable=false.
"""

from __future__ import annotations

import datetime
import os
import re
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
    {"url": "https://mac.example.ts.net/litellm/", "label": "LiteLLM Proxy (HTTPS)", "group": "mac"},
    {"url": "http://localhost:6736/v1/limits", "label": "OpenUsage Limits API", "group": "mac"},
    {"url": "ssh://mac.example.ts.net:22", "label": "SSH Server (sshd)", "group": "mac"},
    {"url": "et://mac.example.ts.net:2022", "label": "Eternal Terminal (etserver)", "group": "mac"},
    {"url": "ard://mac.example.ts.net:3283", "label": "Apple Remote Desktop (ARD)", "group": "mac"},
    {"url": "http://localhost:8080", "label": "Caddy Health", "group": "mac"},
    {"url": "ssh://p7a.example.ts.net:22", "label": "KVM Linux SSH (p7a-kvm)", "group": "p7a"},
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
_ESCAPED_TAG_RE = re.compile(
    r"&lt;/?(?:html|head|body|div|script|link|main|section|article|p|h[1-6])(?:[\s&gt;])", re.I
)


class _StaticAssetParser(HTMLParser):
    """Collect fetchable stylesheet and script URLs without executing page code."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.urls.append(str(values["src"]))
        elif tag == "link" and values.get("href"):
            self.urls.append(str(values["href"]))


class _NoRedirect(HTTPRedirectHandler):
    """Keep expected redirects observable instead of silently following them."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


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
    """Catalog services with example.ts.net and localhost rewritten to the site front-door host."""
    host = _site_caddy_public_hostname(site_dir)
    if not host:
        return list(KNOWN_SERVICES)
    # Derive the tailnet domain from the public host (e.g. "mac.greyhound-sidemirror.ts.net" → "greyhound-sidemirror.ts.net")
    tailnet_domain = host.split(".", 1)[1] if "." in host else host
    out: list[dict] = []
    for entry in KNOWN_SERVICES:
        item = dict(entry)
        url = str(item.get("url") or "")
        label = str(item.get("label") or "")
        if _CATALOG_PUBLIC_HOST in url:
            item["url"] = url.replace(_CATALOG_PUBLIC_HOST, host)
        elif ".example.ts.net" in url:
            # Rewrite any <subdomain>.example.ts.net → <subdomain>.<tailnet_domain>
            import re as _re

            item["url"] = _re.sub(r"([a-z0-9_-]+)\.example\.ts\.net", lambda m: f"{m.group(1)}.{tailnet_domain}", url)
        elif "localhost" in url:
            item["url"] = url.replace("localhost", host)
            if "(localhost)" in label:
                item["label"] = label.replace("(localhost)", "(HTTP)")
        out.append(item)
    return out


def _probe_url(url: str, public_host: str | None) -> str:
    """Use loopback for a local HTTP listener advertised through the site host."""
    if not public_host or public_host not in url or not url.startswith("http://"):
        return url
    m = re.match(r"http://" + re.escape(public_host) + r":(\d+)(.*)", url)
    return f"http://127.0.0.1:{m.group(1)}{m.group(2)}" if m else url


def _http_probe(url: str, timeout: float = 3.0, public_host: str | None = None, **_kwargs) -> int | None:
    """Return HTTP status code (or 200 for open TCP non-HTTP services) or None if unreachable."""
    if url.startswith(("ssh://", "et://", "adb://", "ard://", "tcp://", "launchd://")):
        parts = url.split("://", 1)[1].split("/")[0]
        if url.startswith("launchd://"):
            try:
                import os

                uid = os.getuid()
                r = subprocess.run(
                    ["launchctl", "print", f"gui/{uid}/{parts}"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if r.returncode == 0 and "state = running" in r.stdout:
                    return 200
                return None
            except (OSError, subprocess.TimeoutExpired):
                return None

        if ":" in parts:
            h, p_str = parts.rsplit(":", 1)
            try:
                p = int(p_str)
            except ValueError:
                p = 22
        else:
            h, p = parts, 22

        if public_host and public_host in h:
            h = "127.0.0.1"
        return 200 if _tcp_probe(h, p, timeout=timeout) else None

    probe_url = _probe_url(url, public_host)

    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", str(int(timeout)), probe_url],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        code = r.stdout.strip()
        return int(code) if code.isdigit() and code != "000" else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _http_response(url: str, timeout: float = 3.0, public_host: str | None = None) -> tuple[int, str, str] | None:
    """Fetch one HTTP response without following redirects.

    This deliberately uses only the standard library and never executes page
    JavaScript.  A response body is capped because discovery runs frequently.
    """
    request = Request(_probe_url(url, public_host), headers={"User-Agent": "stayturgid-landing-discover"})
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(1_048_576).decode("utf-8", errors="replace")
            return response.status, response.headers.get_content_type(), body
    except HTTPError as error:
        body = error.read(1_048_576).decode("utf-8", errors="replace")
        return error.code, error.headers.get_content_type(), body
    except (HTTPException, OSError, URLError, ValueError):
        return None


def _is_success_status(status: int, service: Mapping[str, Any]) -> bool:
    """Accept 2xx responses by default plus a catalogued status allowlist."""
    allowed = service.get("accepted_status_codes", [])
    return 200 <= status < 300 or (isinstance(allowed, list) and status in allowed)


def _validate_html_content(
    url: str, body: str, service: Mapping[str, Any], timeout: float = 3.0, public_host: str | None = None
) -> list[str]:
    """Return static HTML problems: escaped markup, missing marker, or assets."""
    problems: list[str] = []
    if _ESCAPED_TAG_RE.search(body):
        problems.append("response contains escaped HTML markup")

    marker = service.get("must_contain")
    if isinstance(marker, str) and marker and marker not in body:
        problems.append(f"response missing required marker: {marker}")

    parser = _StaticAssetParser()
    try:
        parser.feed(body)
    except (ValueError, AssertionError):
        problems.append("response HTML could not be parsed")
        return problems

    for asset in dict.fromkeys(parser.urls):
        asset_url = urljoin(url, asset)
        if asset_url.startswith(("data:", "javascript:", "mailto:", "tel:")):
            continue
        result = _http_response(asset_url, timeout=timeout, public_host=public_host)
        if result is None or result[0] != 200:
            status = "unreachable" if result is None else f"HTTP {result[0]}"
            problems.append(f"asset {asset_url} returned {status}")
    return problems


def _service_health(url: str, service: Mapping[str, Any], *, public_host: str | None = None) -> dict[str, Any]:
    """Classify a service as healthy, degraded, or unreachable.

    ``reachable`` remains a strict successful-response value.  ``health`` is
    separate so a server that answers with HTTP 500 is visibly distinct from
    a host that cannot be reached at all.
    """
    status = _http_probe(url, public_host=public_host)
    if status is None:
        return {"reachable": False, "health": "unreachable"}

    result: dict[str, Any] = {"reachable": _is_success_status(status, service), "status_code": status}
    if not result["reachable"]:
        result.update({"health": "degraded", "health_problems": [f"HTTP {status} is not an accepted success status"]})
        return result

    if not url.startswith(("http://", "https://")):
        result["health"] = "healthy"
        return result

    response = _http_response(url, public_host=public_host)
    if response is None:
        # The inexpensive status probe succeeded. Do not turn a transient
        # body-fetch failure into a green result, and make it diagnosable.
        result.update({"health": "degraded", "health_problems": ["response body could not be fetched"]})
        return result
    _body_status, content_type, body = response
    if content_type != "text/html":
        result["health"] = "healthy"
        return result

    problems = _validate_html_content(url, body, service, public_host=public_host)
    result.update({"health": "healthy" if not problems else "degraded", "content_ok": not problems})
    if problems:
        result["health_problems"] = problems
    return result


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_registry_paths_path(site_dir: Path) -> Path | None:
    candidate = site_dir / "registry" / "paths.yml"
    return candidate if candidate.is_file() else None


def load_dashboard_brew_services(
    registry_path: Path | None = None,
    *,
    site_dir: Path | None = None,
) -> dict[str, str]:
    path = registry_path
    if path is None:
        if site_dir is None:
            selection = _resolve_site(os.environ)
            site_dir = selection.path
        path = _resolve_registry_paths_path(site_dir)
    if path is None or not path.is_file():
        return {}
    if yaml is None:
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}

    services_map: dict[str, str] = {}
    prefixes = doc.get("prefixes") if isinstance(doc, dict) else None
    brew_services = prefixes.get("brew_services") if isinstance(prefixes, dict) else None
    if isinstance(brew_services, list):
        for entry in brew_services:
            if isinstance(entry, dict) and entry.get("dashboard") is True:
                label = entry.get("label")
                if isinstance(label, str):
                    services_map[label] = _format_service_label(label.replace("homebrew.mxcl.", ""))
    return services_map


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
    "OpenUsage": "OpenUsage Limits API",
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
        "openusage-limits": "OpenUsage Limits API",
    }
    if name in replacements:
        return replacements[name]
    return name.replace("-", " ").replace("_", " ").title()


def _parse_ports_yaml_fallback_entries(path: Path) -> dict[int, dict[str, object]]:
    """Crude parser used only when PyYAML is unavailable.

    Real registry entries are flow-mapping style (`- {port: N, bind: "X",
    ...}`) but routinely wrap across 2-3 physical lines (a long note, a
    list-valued caddy_path) -- so this accumulates each entry's full
    `{...}` block (by brace depth) before matching fields, rather than
    assuming one entry = one line, which would silently miss bind/
    caddy_path/tailscale_serve_port whenever they landed on a continuation
    line rather than the same line as `port:`.
    """
    res: dict[int, dict[str, object]] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return res

    port_re = re.compile(r"port:\s*(\d+)")
    svc_re = re.compile(r"service:\s*([a-zA-Z0-9_-]+)")
    bind_re = re.compile(r'bind:\s*"([^"]*)"')
    caddy_path_re = re.compile(r"caddy_path:\s*(\[[^\]]*\]|\"[^\"]*\")")
    tsp_re = re.compile(r"tailscale_serve_port:\s*(\d+)")

    block: list[str] = []
    depth = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if depth == 0:
            if line.startswith("#") or "{" not in line:
                continue
            block = []
        block.append(line)
        depth += line.count("{") - line.count("}")
        if depth > 0:
            continue
        blob = " ".join(block)
        block = []
        pm = port_re.search(blob)
        if not pm:
            continue
        p = int(pm.group(1))
        sm = svc_re.search(blob)
        bm = bind_re.search(blob)
        cm = caddy_path_re.search(blob)
        tm = tsp_re.search(blob)
        entry: dict[str, object] = {"service": sm.group(1) if sm else f"Port {p}"}
        if bm:
            entry["bind"] = bm.group(1)
        if cm:
            # Only truthiness is ever checked on this field -- the raw
            # matched text (a quoted string or a bracketed list literal) is
            # fine as-is, no need to actually parse the list.
            entry["caddy_path"] = cm.group(1)
        if tm:
            entry["tailscale_serve_port"] = tm.group(1)
        res[p] = entry
    return res


def _parse_ports_yaml_fallback(path: Path) -> dict[int, str]:
    entries = _parse_ports_yaml_fallback_entries(path)
    return {p: str(e.get("service", f"Port {p}")) for p, e in entries.items()}


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


# lsof binds and registry `bind` values that mean "loopback only, never
# reachable via the public Tailscale hostname" -- shared by _scan_localhost's
# lsof-based detection and load_loopback_only_registered_ports' registry-based
# detection below, so the two can't drift apart on what counts as loopback.
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _ports_matching(doc: object, predicate: Callable[[dict], bool]) -> set[int]:
    """Return ports from a parsed registry doc whose entry satisfies *predicate*.

    Scans both ``hosts.*.ports`` and ``product_defaults.*`` -- the same two
    sources load_registered_ports itself ingests -- so a skip-list function
    can't silently diverge from what counts as "registered" just because a
    matching field happened to live under product_defaults instead of a
    concrete host entry.
    """
    ports: set[int] = set()

    def _ingest(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("port"), int) and predicate(entry):
                ports.add(entry["port"])

    hosts = doc.get("hosts") if isinstance(doc, dict) else None
    if isinstance(hosts, dict):
        for host_data in hosts.values():
            if isinstance(host_data, dict):
                _ingest(host_data.get("ports"))
    product_defaults = doc.get("product_defaults") if isinstance(doc, dict) else None
    if isinstance(product_defaults, dict):
        for group_entries in product_defaults.values():
            _ingest(group_entries)

    return ports


def _load_registry_doc(registry_path: Path | None, site_dir: Path | None) -> object | None:
    """Resolve and parse the registry file, or None if unavailable/unparseable.

    When PyYAML is unavailable, falls back to the same crude line-based
    parser load_registered_ports uses, wrapped into the same hosts/ports doc
    shape _ports_matching already knows how to scan -- so the bind/
    caddy_path/tailscale_serve_port skip-list functions don't silently
    regress to "nothing registered" just because yaml is missing. That
    would resurrect the exact bug this module fixes: a loopback-only port
    re-advertised via the public hostname, or a Caddy/tailscale-serve
    backend's raw port re-appearing as an unregistered dead link.
    """
    path = registry_path
    if path is None:
        if site_dir is None:
            selection = _resolve_site(os.environ)
            site_dir = selection.path
        path = _resolve_registry_ports_path(site_dir)
    if path is None or not path.is_file():
        return None
    if yaml is None:
        entries = _parse_ports_yaml_fallback_entries(path)
        return {"hosts": {"_fallback": {"ports": [{"port": p, **e} for p, e in entries.items()]}}}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None


def load_loopback_only_registered_ports(
    registry_path: Path | None = None,
    *,
    site_dir: Path | None = None,
) -> set[int]:
    """Return registered ports whose registry entry declares a loopback ``bind``.

    discover()'s "registered ports" seeding loop (below) creates a raw-port
    dashboard entry for every registered port using the public Tailscale
    hostname unconditionally -- it has no bind-awareness at all, unlike
    _scan_localhost's lsof-based detection. That's fine for a port that's
    genuinely reachable off-box, but wrong (and misleading -- a live,
    clickable dead link) for one that's registered with ``bind: "127.0.0.1"``
    and only reachable via Caddy/tailscale-serve/etc. Confirmed real
    2026-08-03: Open WebUI's raw registered-port entry advertised the public
    hostname on a loopback-only port. Consumer: discover()'s registered-ports
    loop uses this to pick 127.0.0.1 instead of the public host and apply the
    same [loopback-only] badge _scan_localhost already applies.
    """
    doc = _load_registry_doc(registry_path, site_dir)
    if doc is None:
        return set()
    return _ports_matching(doc, lambda entry: str(entry.get("bind") or "").strip() in LOOPBACK_HOSTS)


def load_caddy_proxied_ports(
    registry_path: Path | None = None,
    *,
    site_dir: Path | None = None,
) -> set[int]:
    """Return ports whose registry entry declares a ``caddy_path``.

    A backend with ``caddy_path`` set is already reverse_proxy'd by Caddy and
    shown on the dashboard under its real HTTPS route (KNOWN_SERVICES /
    services.json), so ``_scan_localhost`` skips it to avoid a redundant
    raw-port ``[loopback-only]`` duplicate. ``caddy_path`` is an optional,
    additive registry field (see registry/ports.yml's header comment in
    site-djbclark) -- a registry with no such field simply yields no skips.
    """
    doc = _load_registry_doc(registry_path, site_dir)
    if doc is None:
        return set()
    return _ports_matching(doc, lambda entry: bool(entry.get("caddy_path")))


def load_tailscale_serve_ports(
    registry_path: Path | None = None,
    *,
    site_dir: Path | None = None,
) -> set[int]:
    """Return ports whose registry entry declares a ``tailscale_serve_port``.

    Same skip-list purpose as ``load_caddy_proxied_ports`` (avoid a
    redundant raw-port scan duplicate once a backend's real external route
    is already shown), but for a backend exposed via ``tailscale serve
    --https=<port>`` directly instead of a Caddy subpath -- e.g. open-webui,
    which has no reverse-proxy-subpath support at all. Kept as a separate
    function rather than folded into load_caddy_proxied_ports so neither
    one's name/behavior changes for existing callers.
    """
    doc = _load_registry_doc(registry_path, site_dir)
    if doc is None:
        return set()
    return _ports_matching(doc, lambda entry: bool(entry.get("tailscale_serve_port")))


# Caddy's own front-door listeners -- not a proxied backend (no caddy_path
# entry makes sense for these), but still worth skipping in the raw-port scan
# since they're already shown via their registry entries (caddy-http-redirect,
# caddy-https) with a better label than the generic PROCESS_SERVICE_NAMES
# "Caddy Web Server" fallback the scan would otherwise apply.
CADDY_FRONT_DOOR_PORTS: set[int] = {80, 443}


def _scan_localhost(
    *,
    registered_ports: set[int] | dict[int, str] | None = None,
    public_host: str | None = None,
    skip_ports: set[int] | None = None,
) -> list[dict]:
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

    # lsof -n prints the literal bind address, not just the port -- "127.0.0.1:N"
    # for loopback-only, "*:N" (macOS convention for INADDR_ANY) or a real
    # external/Tailscale IP for anything actually reachable off-box. A service
    # bound to loopback can NEVER be reached via the public Tailscale hostname
    # no matter what the health probe says, because nothing is listening on
    # the interface that hostname resolves to -- confirmed real 2026-08-02:
    # Open WebUI bound to 127.0.0.1:8085 probed "up" (loopback answers fine)
    # while every external client got connection refused, and the dashboard
    # had no way to tell the difference because it only ever probed loopback
    # in the first place, then advertised the public hostname anyway.
    host_name = public_host if public_host else "localhost"
    scanned: set[int] = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 9 or "LISTEN" not in line:
            continue
        proc_cmd = parts[0]
        addr = parts[8]
        if ":" not in addr:
            continue
        bind_host, _, port_str = addr.rpartition(":")
        bind_host = bind_host.strip("[]")  # lsof brackets IPv6, e.g. "[::1]:port"
        try:
            port = int(port_str)
        except ValueError:
            continue
        if port in scanned or port < 1 or port > 65535:
            continue
        if skip_ports and port in skip_ports:
            continue
        scanned.add(port)

        status = _http_probe(f"http://127.0.0.1:{port}", timeout=2.0)
        if status is not None:
            unregistered = registered_ports is not None and port not in reg_set
            loopback_only = bind_host in LOOPBACK_HOSTS

            # Resolve descriptive service label
            if port in reg_map and reg_map[port] and not reg_map[port].startswith("TODO"):
                base_label = _format_service_label(reg_map[port])
            elif proc_cmd in PROCESS_SERVICE_NAMES:
                base_label = PROCESS_SERVICE_NAMES[proc_cmd]
            else:
                base_label = f"Port {port}"

            label = base_label
            if loopback_only:
                # Visible on the dashboard itself, not just in `note` -- the
                # template only ever renders label/url/reachable, so a
                # loopback-only service that looked identical to a real
                # externally-reachable one is exactly how this went unnoticed
                # the first time.
                label += " [loopback-only]"
            if unregistered:
                label += " [unregistered]"
            note = f"HTTP {status}"
            if loopback_only:
                note += " (loopback-only -- not reachable via Tailscale/LAN)"
            if unregistered:
                note += "; not in registry/ports.yml"
            entry: dict[str, Any] = {
                # Advertise the URL that's actually true: a loopback-only
                # service is only ever reachable at 127.0.0.1, so linking the
                # public hostname would be a live, clickable dead end.
                "url": f"http://127.0.0.1:{port}" if loopback_only else f"http://{host_name}:{port}",
                "label": label,
                "group": "mac",
                "note": note,
            }
            if loopback_only:
                entry["loopback_only"] = True
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

    # Purge un-rewritten catalog placeholder URLs (e.g., mac.example.ts.net) and legacy http://localhost: entries when a real site host exists
    public_host = _site_caddy_public_hostname(site_dir)
    if public_host:
        for url_key in list(known_urls.keys()):
            if (
                _CATALOG_PUBLIC_HOST in url_key
                or ".example.ts.net" in url_key
                or url_key.startswith("http://localhost:")
            ):
                del known_urls[url_key]

    # Add/update known services (site MagicDNS substituted for catalog placeholder)
    catalog_urls: set[str] = set()
    catalog_urls_by_identity: dict[tuple[str | None, str | None], set[str]] = {}
    for s in _known_services_for_site(site_dir):
        url = s["url"]
        catalog_urls.add(url)
        catalog_urls_by_identity.setdefault((s.get("label"), s.get("group")), set()).add(url)
        if url in known_urls:
            known_urls[url].update({k: v for k, v in s.items() if k != "url"})
        else:
            known_urls[url] = dict(s)

    # Purge a stale entry for a catalog-tracked service whose URL simply
    # changed between deploys -- e.g. Open WebUI moving from a Caddy
    # /chat/* subpath to a dedicated tailscale-serve port. Nothing else
    # ever cleans this up: the old URL isn't a "registered port" skip-list
    # match, isn't flagged unregistered, and doesn't start with
    # http://localhost:, so it survives every existing prune path forever
    # (even once genuinely unreachable) and shows a duplicate dashboard
    # row for the same logical service. Identity is (label, group) since
    # that's what stays stable across a catalog URL edit. Confirmed real
    # 2026-08-03: this was still showing the pre-fix /chat/ URL alongside
    # the new :8086/ URL after this exact class of catalog change deployed.
    for url in list(known_urls.keys()):
        entry = known_urls[url]
        valid_urls = catalog_urls_by_identity.get((entry.get("label"), entry.get("group")))
        if valid_urls and url not in valid_urls:
            del known_urls[url]

    # Discover new http ports on localhost; badge registry drift (D4).
    registered = load_registered_ports(site_dir=site_dir, return_map=True)

    path_ports: set[int] = set()
    for url in known_urls:
        try:
            if url.startswith("http"):
                base = url.split("://", 1)[1]
                if "/" in base:
                    host_port, path = base.split("/", 1)
                    if ":" in host_port:
                        port = int(host_port.split(":")[-1])
                        if path and path != "":
                            path_ports.add(port)
        except ValueError:
            pass

    for url in list(known_urls.keys()):
        try:
            if url.startswith("http"):
                base = url.split("://", 1)[1]
                if "/" in base:
                    host_port, path = base.split("/", 1)
                    if (not path or path == "") and ":" in host_port:
                        port = int(host_port.split(":")[-1])
                        if port in path_ports:
                            del known_urls[url]
                else:
                    if ":" in base:
                        port = int(base.split(":")[-1])
                        if port in path_ports:
                            del known_urls[url]
        except ValueError:
            pass

    if registered:
        loopback_only_registered = load_loopback_only_registered_ports(site_dir=site_dir)
        for port, svc_name in registered.items():
            if port not in path_ports:
                loopback_only = port in loopback_only_registered
                # A registered port with bind:127.0.0.1 can never be reached
                # via the public Tailscale hostname, no matter what this
                # loop advertises -- match _scan_localhost's own bind-aware
                # URL choice and [loopback-only] badge instead of always
                # using the public host. Confirmed real 2026-08-03: this
                # loop advertised Open WebUI's registered raw port via the
                # public hostname even though it was loopback-only, a live
                # dead link on the dashboard.
                host_name = "127.0.0.1" if loopback_only else (public_host if public_host else "localhost")
                url = f"http://{host_name}:{port}"
                fresh_label = _format_service_label(svc_name)
                if loopback_only:
                    fresh_label += " [loopback-only]"
                    # A raw (no-path) entry for this exact port can persist
                    # under a different, now-wrong host key forever
                    # otherwise -- e.g. the public-hostname URL a prior run
                    # created before this port was known to be
                    # loopback-only. Clean those up so the dashboard doesn't
                    # show a stale broken-link row alongside the correct
                    # one. Never touches a different, legitimately distinct
                    # path-routed entry for the same port (those have a
                    # path component, so the bare f"http://{host}:{port}"
                    # key never matches them), nor a catalog-declared static
                    # entry that happens to share this port number -- only a
                    # prior run's own leftover raw-port entry is fair game.
                    # Confirmed real 2026-08-03: an unguarded version of this
                    # cleanup deleted a legitimate static catalog entry whose
                    # port collided with an unrelated newly-loopback-only
                    # registered port.
                    for other_host in ("127.0.0.1", "localhost", public_host):
                        if not other_host:
                            continue
                        stale_url = f"http://{other_host}:{port}"
                        if stale_url != url and stale_url not in catalog_urls:
                            known_urls.pop(stale_url, None)
                else:
                    # Symmetric cleanup for the reverse transition: a port
                    # that used to be loopback-only (bind widened to 0.0.0.0
                    # or the registry entry removed) can leave behind a
                    # stale 127.0.0.1 raw-port entry from a prior run,
                    # duplicating the service on the dashboard under a wrong,
                    # now-mislabeled [loopback-only] row alongside the new
                    # public-host entry. 127.0.0.1 still answers after the
                    # bind widens, so this isn't a dead link like the
                    # forward direction -- just a stale duplicate.
                    stale_url = f"http://127.0.0.1:{port}"
                    if stale_url != url and stale_url not in catalog_urls:
                        known_urls.pop(stale_url, None)
                if url not in known_urls:
                    entry: dict[str, Any] = {
                        "url": url,
                        "label": fresh_label,
                        "group": "mac",
                    }
                    if loopback_only:
                        entry["loopback_only"] = True
                        entry["note"] = "loopback-only -- not reachable via Tailscale/LAN"
                    known_urls[url] = entry
                else:
                    # A raw-port entry carried over from a prior state.json
                    # can get stuck with a stale label/note forever once its
                    # port becomes Caddy-proxied (load_caddy_proxied_ports)
                    # and _scan_localhost stops revisiting it -- nothing else
                    # ever refreshes this entry again. Confirmed real
                    # 2026-08-03: Open WebUI's raw :8085 entry stayed badged
                    # "not in registry/ports.yml" after it became both
                    # registered and caddy-skipped in the same deploy.
                    entry = known_urls[url]
                    entry["label"] = fresh_label
                    entry.pop("unregistered", None)
                    note = entry.get("note")
                    if isinstance(note, str) and "not in registry/ports.yml" in note:
                        cleaned = (
                            note.replace("; not in registry/ports.yml", "")
                            .replace("not in registry/ports.yml", "")
                            .strip("; ")
                        )
                        if cleaned:
                            entry["note"] = cleaned
                        else:
                            entry.pop("note", None)

    dashboard_services = load_dashboard_brew_services(site_dir=site_dir)
    for label, formatted_label in dashboard_services.items():
        url = f"launchd://{label}"
        if url not in known_urls:
            known_urls[url] = {
                "url": url,
                "label": formatted_label,
                "group": "mac",
            }

    caddy_proxied_ports = load_caddy_proxied_ports(site_dir=site_dir)
    tailscale_serve_ports = load_tailscale_serve_ports(site_dir=site_dir)
    externally_routed_ports = path_ports | caddy_proxied_ports | tailscale_serve_ports | CADDY_FRONT_DOOR_PORTS
    for s in _scan_localhost(
        registered_ports=registered if registered else None,
        public_host=public_host,
        skip_ports=externally_routed_ports,
    ):
        url = s["url"]
        if url not in known_urls:
            known_urls[url] = s
        else:
            # Refresh label and unregistered badge status on existing entries
            known_urls[url]["label"] = s["label"]
            if s.get("unregistered"):
                known_urls[url]["unregistered"] = True
            else:
                known_urls[url].pop("unregistered", None)
    # Discover non-HTTP services (Termux SSH, Wireless ADB) on detected Android devices
    device_names = {
        state._extract_device_name(s) for s in known_urls.values() if s.get("group") in ("devices", "android")
    }
    for dev_name in device_names:
        if dev_name not in state.EXAMPLE_DEVICE_NAMES:
            domain = public_host.split(".", 1)[1] if (public_host and "." in public_host) else "example.ts.net"
            dev_fqdn = f"{dev_name}.{domain}"
            ssh_url = f"ssh://{dev_fqdn}:8022"
            adb_url = f"adb://{dev_fqdn}:5555"
            if ssh_url not in known_urls:
                known_urls[ssh_url] = {"url": ssh_url, "label": f"{dev_name} Termux SSH", "group": "devices"}
            if adb_url not in known_urls:
                known_urls[adb_url] = {"url": adb_url, "label": f"{dev_name} Wireless ADB", "group": "devices"}

    # Probe reachability
    hidden = set(existing.get("hidden", []))
    services: list[dict] = []
    static_urls = {ks["url"] for ks in _known_services_for_site(site_dir)}
    for url, s in sorted(known_urls.items()):
        s["url"] = url
        for field in ("content_ok", "health_problems"):
            s.pop(field, None)
        health = _service_health(url, s, public_host=public_host)
        s.update(health)
        if health["health"] != "unreachable":
            s["last_seen"] = now
            if url not in hidden:
                services.append(s)
        else:
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

    services = state.filter_example_devices(services)
    services.sort(key=state.service_sort_key)
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


def get_summary_counts(
    result: dict,
    registered: set[int] | dict[int, str],
    static_urls: set[str],
    dashboard_urls: set[str] | None = None,
) -> dict[str, int]:
    dashboard_urls = dashboard_urls or set()
    reachable = 0
    total = len(result["services"])
    unregistered_up = 0
    registered_down = 0
    catalog_unreachable = 0

    for s in result["services"]:
        is_up = s.get("reachable", False)
        if is_up:
            reachable += 1

        url = s["url"]
        port = None
        try:
            if "://" in url:
                part = url.split("://", 1)[1].split("/", 1)[0]
                if ":" in part:
                    port = int(part.split(":")[-1])
        except ValueError:
            pass

        is_reg = (port is not None and port in registered) or url in dashboard_urls
        is_cat = url in static_urls

        if is_cat and not is_up:
            catalog_unreachable += 1
        elif is_reg and not is_up:
            registered_down += 1

        if s.get("unregistered") and is_up:
            unregistered_up += 1

    return {
        "reachable": reachable,
        "total": total,
        "unregistered_up": unregistered_up,
        "registered_down": registered_down,
        "catalog_unreachable": catalog_unreachable,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--health-check", action="store_true", help="Run discovery and exit non-zero if registered services are down"
    )
    args = parser.parse_args(argv)

    try:
        result = discover()
    except SiteDiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    import os

    selection = _resolve_site(os.environ)
    registered = load_registered_ports(site_dir=selection.path)
    static_urls = {ks["url"] for ks in _known_services_for_site(selection.path)}
    dashboard_services = load_dashboard_brew_services(site_dir=selection.path)
    dashboard_urls = {f"launchd://{label}" for label in dashboard_services}

    summary = get_summary_counts(result, registered, static_urls, dashboard_urls)

    reachable = summary["reachable"]
    total = summary["total"]
    registered_down = summary["registered_down"]
    unregistered_up = summary["unregistered_up"]
    catalog_unreachable = summary["catalog_unreachable"]

    print(f"Discovery complete: {reachable}/{total} services reachable")
    print(
        f"Summary: {registered_down} registered-down, {unregistered_up} unregistered-up, {catalog_unreachable} catalog-unreachable"
    )
    if unregistered_up:
        print(f"Registry drift: {unregistered_up} unregistered listener(s) (not in registry/ports.yml)")
    for s in result["services"]:
        status = "✓" if s.get("reachable") else "✗"
        badge = " [unregistered]" if s.get("unregistered") else ""
        print(f"  {status} {s['url']:50s} — {s['label']}{badge if badge not in s.get('label', '') else ''}")

    if args.health_check and registered_down > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
