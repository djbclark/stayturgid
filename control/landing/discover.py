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
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_LIB = _REPO / "control" / "lib"
sys.path.insert(0, str(_REPO))

from control.landing import state  # noqa: E402

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional for bare runs
    yaml = None  # type: ignore[assignment]

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
    {"url": "http://localhost:8081", "label": "VLM UI-TARS API", "group": "mac"},
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


def _site_caddy_public_hostname() -> str | None:
    """Read caddy_public_hostname from site inventory group_vars if present."""
    env_dir = os.environ.get("STAYTURGID_SITE_DIR", "").strip()
    candidates: list[Path] = []
    if env_dir:
        candidates.append(Path(env_dir).expanduser() / "inventory" / "group_vars" / "all.yml")
    ops_root = Path(os.environ.get("OPS_ROOT", Path.home() / "ops")).expanduser()
    if ops_root.is_dir():
        for site in sorted(p for p in ops_root.glob("site-*") if p.is_dir()):
            candidates.append(site / "inventory" / "group_vars" / "all.yml")
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


def _known_services_for_site() -> list[dict]:
    """Catalog services with example.ts.net rewritten to the site front-door host."""
    host = _site_caddy_public_hostname()
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


def _resolve_registry_ports_path() -> Path | None:
    """Locate site registry/ports.yml (STAYTURGID_SITE_DIR or OPS_ROOT/site-*)."""
    env_dir = os.environ.get("STAYTURGID_SITE_DIR", "").strip()
    if env_dir:
        candidate = Path(env_dir).expanduser() / "registry" / "ports.yml"
        if candidate.is_file():
            return candidate
    ops_root = Path(os.environ.get("OPS_ROOT", Path.home() / "ops")).expanduser()
    if ops_root.is_dir():
        sites = sorted(p for p in ops_root.glob("site-*") if p.is_dir())
        if len(sites) == 1:
            candidate = sites[0] / "registry" / "ports.yml"
            if candidate.is_file():
                return candidate
    return None


def load_registered_ports(registry_path: Path | None = None) -> set[int]:
    """Return the set of ports declared in the site registry (any host)."""
    path = registry_path if registry_path is not None else _resolve_registry_ports_path()
    if path is None or not path.is_file() or yaml is None:
        return set()
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    ports: set[int] = set()

    def _ingest(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("port"), int):
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


def _scan_localhost(*, registered_ports: set[int] | None = None) -> list[dict]:
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

    scanned: set[int] = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 9 or "LISTEN" not in line:
            continue
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
            unregistered = registered_ports is not None and port not in registered_ports
            label = f"Port {port}" + (" [unregistered]" if unregistered else "")
            note = f"HTTP {status}"
            if unregistered:
                note += "; not in registry/ports.yml"
            entry = {
                "url": f"http://localhost:{port}",
                "label": label,
                "group": "mac",
                "note": note,
            }
            if unregistered:
                entry["unregistered"] = True
            services.append(entry)

    return services


def discover() -> dict:
    """Run a full discovery scan. Returns the updated catalog."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing: dict = state.load_state()

    # Start with known services, merge with existing
    known_urls: dict[str, dict] = {}
    for s in existing.get("services", []):
        known_urls[s["url"]] = s

    # Add/update known services (site MagicDNS substituted for catalog placeholder)
    for s in _known_services_for_site():
        url = s["url"]
        if url in known_urls:
            known_urls[url].update({k: v for k, v in s.items() if k != "url"})
        else:
            known_urls[url] = dict(s)

    # Discover new http ports on localhost; badge registry drift (D4).
    registered = load_registered_ports()
    for s in _scan_localhost(registered_ports=registered if registered else None):
        url = s["url"]
        if url not in known_urls:
            known_urls[url] = s
        elif s.get("unregistered"):
            # Refresh badge on already-catalogued dynamic entries
            known_urls[url]["unregistered"] = True
            if "[unregistered]" not in known_urls[url].get("label", ""):
                known_urls[url]["label"] = f"{known_urls[url].get('label', url)} [unregistered]"

    # Probe reachability
    hidden = set(existing.get("hidden", []))
    services: list[dict] = []
    for url, s in sorted(known_urls.items()):
        s["url"] = url
        status = _http_probe(url)
        if status is not None:
            s["reachable"] = True
            s["last_seen"] = now
            s["status_code"] = status
        else:
            s["reachable"] = False
            if s.get("last_seen") is None:
                # Might just be down temporarily; also try TCP
                host = url.split("://")[1].split(":")[0]
                try:
                    port = int(url.rsplit(":", 1)[-1])
                except ValueError:
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
    result = discover()
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
