#!/usr/bin/env python3
"""Network service discovery — scans local and Tailscale hosts for HTTP servers.

Updates user-local landing state with reachability and last-seen timestamps.
Designed to run periodically (via launchd or cron). Never removes entries —
unreachable services stay in the catalog with reachable=false.
"""

from __future__ import annotations

import datetime
import socket
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_LIB = _REPO / "control" / "lib"
sys.path.insert(0, str(_REPO))

from control.landing import state  # noqa: E402

SERVICES_FILE = state.STATE_FILE

# ── Known service definitions (URL, label, group) ───────────────────────────
KNOWN_SERVICES: list[dict] = [
    # Mac control node — all served via Caddy HTTPS
    {"url": "https://mac.example.ts.net", "label": "Network Landing (root)", "group": "mac"},
    {"url": "https://mac.example.ts.net/opencode/", "label": "OpenCode Web (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/dashboard/", "label": "Fleet Dashboard (HTTPS)", "group": "mac"},
    {"url": "https://mac.example.ts.net/stats/", "label": "Fleet Stats (HTTPS)", "group": "mac"},
    # Localhost (direct, for Mac-only access)
    {"url": "http://localhost:4096", "label": "OpenCode (localhost)", "group": "mac"},
    {"url": "http://localhost:4097", "label": "Dashboard (localhost)", "group": "mac"},
    {"url": "http://localhost:4097/stats", "label": "Stats (localhost)", "group": "mac"},
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


def _scan_localhost() -> list[dict]:
    """Scan the Mac's local ports for HTTP servers using lsof."""
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
            services.append(
                {
                    "url": f"http://localhost:{port}",
                    "label": f"Port {port}",
                    "group": "mac",
                    "note": f"HTTP {status}",
                }
            )

    return services


def discover() -> dict:
    """Run a full discovery scan. Returns the updated catalog."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing: dict = state.load_state()

    # Start with known services, merge with existing
    known_urls: dict[str, dict] = {}
    for s in existing.get("services", []):
        known_urls[s["url"]] = s

    # Add/update known services
    for s in KNOWN_SERVICES:
        url = s["url"]
        if url in known_urls:
            known_urls[url].update({k: v for k, v in s.items() if k != "url"})
        else:
            known_urls[url] = dict(s)

    # Discover new http ports on localhost
    for s in _scan_localhost():
        url = s["url"]
        if url not in known_urls:
            known_urls[url] = s

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
    print(f"Discovery complete: {reachable}/{total} services reachable")
    for s in result["services"]:
        status = "✓" if s.get("reachable") else "✗"
        print(f"  {status} {s['url']:50s} — {s['label']}")
