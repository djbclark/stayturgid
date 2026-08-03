import pytest

from control.landing import discover, state
from control.lib.site_discovery import SiteSelection


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    def mock_resolve(env):
        return SiteSelection(path=site_dir, source="test")

    monkeypatch.setattr(discover, "_resolve_site", mock_resolve)
    monkeypatch.setattr(discover, "announce_site_selection", lambda s, command: None)
    monkeypatch.setattr(state, "write_state", lambda d: None)
    return site_dir


@pytest.fixture
def mock_known_services(monkeypatch):
    monkeypatch.setattr(discover, "_known_services_for_site", lambda site_dir: [])


def test_gap1_registered_not_listening(mock_env, mock_known_services, monkeypatch):
    monkeypatch.setattr(
        discover,
        "load_registered_ports",
        lambda site_dir, return_map=False: {8080: "My Service"} if return_map else {8080},
    )
    monkeypatch.setattr(state, "load_state", lambda: {"services": [], "hidden": []})
    monkeypatch.setattr(discover, "_scan_localhost", lambda **kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: None)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: False)

    result = discover.discover({})

    services = result["services"]
    assert len(services) == 1
    svc = services[0]
    assert svc["url"] == "http://localhost:8080"
    assert svc["reachable"] is False
    assert svc["label"] == "My Service"


def test_retention_registered_unreachable(mock_env, mock_known_services, monkeypatch):
    monkeypatch.setattr(
        discover,
        "load_registered_ports",
        lambda site_dir, return_map=False: {9090: "Old Service"} if return_map else {9090},
    )
    monkeypatch.setattr(
        state,
        "load_state",
        lambda: {
            "services": [
                {
                    "url": "http://localhost:9090",
                    "label": "Old Service",
                    "group": "mac",
                    "reachable": True,
                    "last_seen": "2026-01-01T00:00:00Z",
                }
            ],
            "hidden": [],
        },
    )

    monkeypatch.setattr(discover, "_scan_localhost", lambda **kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: None)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: False)

    result = discover.discover({})

    services = result["services"]
    assert len(services) == 1
    svc = services[0]
    assert svc["url"] == "http://localhost:9090"
    assert svc["reachable"] is False
    assert svc["last_seen"] == "2026-01-01T00:00:00Z"


def test_prune_unregistered_unreachable(mock_env, mock_known_services, monkeypatch):
    monkeypatch.setattr(
        discover, "load_registered_ports", lambda site_dir, return_map=False: {} if return_map else set()
    )
    monkeypatch.setattr(
        state,
        "load_state",
        lambda: {
            "services": [
                {
                    "url": "http://localhost:12345",
                    "label": "Port 12345 [unregistered]",
                    "group": "mac",
                    "unregistered": True,
                    "reachable": True,
                    "last_seen": "2026-01-01T00:00:00Z",
                }
            ],
            "hidden": [],
        },
    )

    monkeypatch.setattr(discover, "_scan_localhost", lambda **kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: None)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: False)

    result = discover.discover({})

    services = result["services"]
    assert len(services) == 0


def test_gap2_dual_row_ambiguity(mock_env, monkeypatch):
    monkeypatch.setattr(
        discover,
        "load_registered_ports",
        lambda site_dir, return_map=False: {6736: "OpenUsage"} if return_map else {6736},
    )
    monkeypatch.setattr(
        discover,
        "_known_services_for_site",
        lambda site_dir: [{"url": "http://localhost:6736/v1/limits", "label": "OpenUsage Limits API", "group": "mac"}],
    )
    monkeypatch.setattr(state, "load_state", lambda: {"services": [], "hidden": []})

    def mock_scan(*, registered_ports=None, public_host=None, skip_ports=None):
        if skip_ports and 6736 in skip_ports:
            return []
        return [{"url": "http://localhost:6736", "label": "OpenUsage", "group": "mac"}]

    monkeypatch.setattr(discover, "_scan_localhost", mock_scan)
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: 200)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: True)

    result = discover.discover({})

    services = result["services"]
    urls = [s["url"] for s in services]
    assert "http://localhost:6736/v1/limits" in urls
    assert "http://localhost:6736" not in urls


def test_stale_registered_entry_label_and_note_are_refreshed(mock_env, mock_known_services, monkeypatch):
    """A raw-port entry carried over from a prior state.json must not stay
    stuck with a stale label/note forever once its port becomes registered
    and Caddy-skipped in the same deploy (_scan_localhost stops revisiting
    it, so nothing else would ever refresh it) -- confirmed real 2026-08-03:
    Open WebUI's raw :8085 entry stayed badged "not in registry/ports.yml"
    after tonight's caddy_path fix made discover.py skip re-scanning it."""
    monkeypatch.setattr(
        discover,
        "load_registered_ports",
        lambda site_dir, return_map=False: {8085: "open-webui"} if return_map else {8085},
    )
    monkeypatch.setattr(
        state,
        "load_state",
        lambda: {
            "services": [
                {
                    "url": "http://localhost:8085",
                    "label": "Open Webui",
                    "group": "mac",
                    "note": "HTTP 200; not in registry/ports.yml",
                    "unregistered": True,
                    "reachable": True,
                    "last_seen": "2026-01-01T00:00:00Z",
                }
            ],
            "hidden": [],
        },
    )
    monkeypatch.setattr(discover, "_scan_localhost", lambda **kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: 200)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: True)

    result = discover.discover({})

    by_url = {s["url"]: s for s in result["services"]}
    entry = by_url["http://localhost:8085"]
    assert entry["label"] == "Open Webui"
    assert "unregistered" not in entry
    assert "not in registry" not in (entry.get("note") or "")


def test_probe_launchd(monkeypatch):
    import subprocess

    def mock_run(*args, **kwargs):
        cmd = args[0]
        if "herdr" in cmd[2]:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="state = running")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="state = stopped")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # test herdr is running
    assert discover._http_probe("launchd://homebrew.mxcl.herdr") == 200
    # test other is not
    assert discover._http_probe("launchd://homebrew.mxcl.other") is None


def test_load_dashboard_brew_services(mock_env, monkeypatch):
    class MockPath:
        def is_file(self):
            return True

        def read_text(self, encoding):
            # brew_services lives nested under `prefixes`, matching the real
            # registry/paths.yml shape — a flat top-level key here would
            # silently hide the bug this test exists to catch.
            return """
prefixes:
  brew_services:
    - {label: homebrew.mxcl.herdr, dashboard: true}
    - {label: homebrew.mxcl.et, dashboard: false}
"""

    monkeypatch.setattr(discover, "_resolve_registry_paths_path", lambda site_dir: MockPath())
    services = discover.load_dashboard_brew_services(site_dir=mock_env)
    assert "homebrew.mxcl.herdr" in services
    assert services["homebrew.mxcl.herdr"] == "Herdr"
    assert "homebrew.mxcl.et" not in services


def test_get_summary_counts():
    result = {
        "services": [
            {"url": "http://localhost:8080", "reachable": True, "unregistered": True},
            {"url": "http://localhost:9090", "reachable": False},
            {"url": "http://localhost:9091", "reachable": False},
            {"url": "launchd://homebrew.mxcl.herdr", "reachable": False},
        ]
    }
    registered = {9090: "Service 9090"}
    static_urls = {"http://localhost:9091"}
    dashboard_urls = {"launchd://homebrew.mxcl.herdr"}

    summary = discover.get_summary_counts(result, registered, static_urls, dashboard_urls)
    assert summary["reachable"] == 1
    assert summary["total"] == 4
    assert summary["unregistered_up"] == 1
    assert summary["registered_down"] == 2  # 9090 and herdr
    assert summary["catalog_unreachable"] == 1  # 9091


def test_main_health_check(mock_env, monkeypatch):
    monkeypatch.setattr(discover, "discover", lambda: {"services": []})
    monkeypatch.setattr(discover, "load_registered_ports", lambda site_dir: {})
    monkeypatch.setattr(discover, "_known_services_for_site", lambda site_dir: [])
    monkeypatch.setattr(discover, "load_dashboard_brew_services", lambda site_dir: {})

    def mock_summary(*args):
        return {"reachable": 0, "total": 0, "registered_down": 1, "unregistered_up": 0, "catalog_unreachable": 0}

    monkeypatch.setattr(discover, "get_summary_counts", mock_summary)

    assert discover.main(["--health-check"]) == 1

    def mock_summary_healthy(*args):
        return {"reachable": 0, "total": 0, "registered_down": 0, "unregistered_up": 0, "catalog_unreachable": 0}

    monkeypatch.setattr(discover, "get_summary_counts", mock_summary_healthy)
    assert discover.main(["--health-check"]) == 0


# ---------------------------------------------------------------------------
# _scan_localhost loopback detection (2026-08-02 real incident: Open WebUI
# bound to 127.0.0.1:8085 was probed and advertised as reachable via the
# public Tailscale hostname on the dashboard, but nothing external could
# ever reach it -- the probe only ever checked loopback, and the URL shown
# to the operator was the public one regardless of what was actually true.)
# ---------------------------------------------------------------------------


def _fake_run_factory(lsof_stdout: str):
    """subprocess.run replacement that answers lsof for real and stubs curl
    (used inside _http_probe) to always report 200, so tests exercise
    _scan_localhost's own bind-address logic in isolation from real probes."""

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lsof":
            return type("R", (), {"returncode": 0, "stdout": lsof_stdout, "stderr": ""})()
        if cmd[0] == "curl":
            return type("R", (), {"returncode": 0, "stdout": "200", "stderr": ""})()
        raise AssertionError(f"unexpected subprocess.run call: {cmd}")

    return fake_run


def test_scan_localhost_flags_loopback_only_service(monkeypatch):
    # 19191 is an arbitrary port -- this test exercises the general
    # loopback-detection mechanism, independent of which specific ports are
    # currently known to be Caddy-proxied.
    lsof_out = "python3.1 93878 djbclark 36u IPv4 0xdead 0t0 TCP 127.0.0.1:19191 (LISTEN)\n"
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    services = discover._scan_localhost(public_host="mac.example.ts.net")

    assert len(services) == 1
    entry = services[0]
    assert entry["url"] == "http://127.0.0.1:19191"
    assert entry.get("loopback_only") is True
    assert "loopback-only" in entry["note"]
    # Visible in the rendered dashboard, not just the JSON: the template only
    # ever shows label/url/reachable, never `note`.
    assert "[loopback-only]" in entry["label"]


def test_scan_localhost_respects_skip_ports(monkeypatch):
    """_scan_localhost itself no longer hardcodes any Caddy-specific port
    list -- callers (discover()) are responsible for computing the skip set
    and passing it in via skip_ports. This confirms the mechanism it now
    relies on entirely."""
    lsof_out = (
        "python3.1 1 djbclark 1u IPv4 0x1 0t0 TCP 127.0.0.1:8085 (LISTEN)\n"
        "python3.1 2 djbclark 2u IPv4 0x2 0t0 TCP 127.0.0.1:19192 (LISTEN)\n"
    )
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    services = discover._scan_localhost(public_host="mac.example.ts.net", skip_ports={8085})

    assert len(services) == 1
    assert services[0]["url"] == "http://127.0.0.1:19192"


def test_load_caddy_proxied_ports(tmp_path):
    """caddy_path is an optional, additive registry/ports.yml field (string
    or list of strings) -- confirmed real 2026-08-02: litellm (4000), the
    landing page's own backend (8088), and Open WebUI (8085) had all been
    added to Caddy without a corresponding entry in the old hardcoded
    CADDY_PROXIED_PORTS set, so they showed up as confusing unlabeled
    loopback-only entries instead of just their one correct HTTPS route.
    This is the registry-driven replacement for that hardcoded list."""
    registry = tmp_path / "ports.yml"
    registry.write_text(
        """
hosts:
  mac:
    ports:
      - {port: 8085, bind: "127.0.0.1", owner: site, service: open-webui, status: active, caddy_path: "/chat/*"}
      - {port: 4097, bind: "127.0.0.1", owner: stayturgid, service: fleet-dashboard, status: active,
         caddy_path: ["/dashboard/*", "/stats/*"]}
      - {port: 6736, bind: "127.0.0.1", owner: site, service: openusage-limits, status: active}
"""
    )

    ports = discover.load_caddy_proxied_ports(registry_path=registry)

    assert ports == {8085, 4097}


def test_load_caddy_proxied_ports_missing_registry(tmp_path):
    ports = discover.load_caddy_proxied_ports(registry_path=tmp_path / "does-not-exist.yml")
    assert ports == set()


def test_discover_skips_caddy_proxied_backend_via_registry(mock_env, mock_known_services, monkeypatch):
    """End-to-end: a caddy_path entry in the site's real registry/ports.yml
    is enough to suppress the raw-port scan duplicate, with no code-level
    port list to maintain."""
    site_dir = mock_env
    registry_dir = site_dir / "registry"
    registry_dir.mkdir()
    (registry_dir / "ports.yml").write_text(
        """
hosts:
  mac:
    ports:
      - {port: 8085, bind: "127.0.0.1", owner: site, service: open-webui, status: active, caddy_path: "/chat/*"}
"""
    )

    monkeypatch.setattr(
        discover, "load_registered_ports", lambda site_dir, return_map=False: {} if return_map else set()
    )
    monkeypatch.setattr(state, "load_state", lambda: {"services": [], "hidden": []})

    lsof_out = "python3.1 1 djbclark 1u IPv4 0x1 0t0 TCP 127.0.0.1:8085 (LISTEN)\n"
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    result = discover.discover({})

    assert result["services"] == []


def test_load_tailscale_serve_ports(tmp_path):
    """tailscale_serve_port is the analogous field to caddy_path for a
    backend exposed via `tailscale serve --https=<port>` directly instead
    of a Caddy subpath -- confirmed real 2026-08-03: Open WebUI has no
    reverse-proxy-subpath support at all, so it moved from caddy_path to
    this field entirely."""
    registry = tmp_path / "ports.yml"
    registry.write_text(
        """
hosts:
  mac:
    ports:
      - {port: 8085, bind: "127.0.0.1", owner: site, service: open-webui, status: active, tailscale_serve_port: 8086}
      - {port: 6736, bind: "127.0.0.1", owner: site, service: openusage-limits, status: active}
"""
    )

    ports = discover.load_tailscale_serve_ports(registry_path=registry)

    assert ports == {8085}


def test_load_loopback_only_registered_ports(tmp_path):
    """Registry entries with bind:127.0.0.1 (or ::1/localhost) are the
    ports discover()'s registered-ports seeding loop must not advertise via
    the public Tailscale hostname -- confirmed real 2026-08-03: it did so
    unconditionally before this fix, producing a live dead link on the
    dashboard for Open WebUI's raw registered port."""
    registry = tmp_path / "ports.yml"
    registry.write_text(
        """
hosts:
  mac:
    ports:
      - {port: 8085, bind: "127.0.0.1", owner: site, service: open-webui, status: active}
      - {port: 443, bind: "*", owner: site, service: caddy-https, status: active}
      - {port: 4318, bind: "0.0.0.0", owner: site, service: vector-otlp-http, status: active}
"""
    )

    ports = discover.load_loopback_only_registered_ports(registry_path=registry)

    assert ports == {8085}


def test_discover_registered_loopback_port_advertises_127001_not_public_host(
    mock_env, mock_known_services, monkeypatch
):
    """End-to-end reproduction of the real 2026-08-03 bug: a registered port
    with bind:127.0.0.1 that ISN'T Caddy/tailscale-serve-skipped must get a
    127.0.0.1 URL and the [loopback-only] badge from the registered-ports
    seeding loop, not the public Tailscale hostname."""
    site_dir = mock_env
    registry_dir = site_dir / "registry"
    registry_dir.mkdir()
    (registry_dir / "ports.yml").write_text(
        """
hosts:
  mac:
    ports:
      - {port: 9999, bind: "127.0.0.1", owner: site, service: loopback-only-app, status: active}
"""
    )
    monkeypatch.setattr(state, "load_state", lambda: {"services": [], "hidden": []})
    monkeypatch.setattr(discover, "_scan_localhost", lambda **kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda url, **kwargs: None)
    monkeypatch.setattr(discover, "_tcp_probe", lambda host, port, **kwargs: False)

    result = discover.discover({})

    by_url = {s["url"]: s for s in result["services"]}
    assert "http://127.0.0.1:9999" in by_url
    assert "http://localhost:9999" not in by_url
    entry = by_url["http://127.0.0.1:9999"]
    assert entry.get("loopback_only") is True
    assert "[loopback-only]" in entry["label"]


def test_scan_localhost_advertises_public_url_for_wildcard_bind(monkeypatch):
    lsof_out = "python3.1 1234 djbclark 12u IPv4 0xbeef 0t0 TCP *:9091 (LISTEN)\n"
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    services = discover._scan_localhost(public_host="mac.example.ts.net")

    assert len(services) == 1
    entry = services[0]
    assert entry["url"] == "http://mac.example.ts.net:9091"
    assert "loopback_only" not in entry
    assert "loopback-only" not in entry["note"]


def test_scan_localhost_advertises_public_url_for_specific_external_bind(monkeypatch):
    lsof_out = "python3.1 1234 djbclark 12u IPv4 0xbeef 0t0 TCP 100.113.53.87:9092 (LISTEN)\n"
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    services = discover._scan_localhost(public_host="mac.example.ts.net")

    assert len(services) == 1
    entry = services[0]
    assert entry["url"] == "http://mac.example.ts.net:9092"
    assert "loopback_only" not in entry


def test_scan_localhost_ipv6_loopback_is_flagged(monkeypatch):
    lsof_out = "node 5555 djbclark 20u IPv6 0xcafe 0t0 TCP [::1]:9093 (LISTEN)\n"
    monkeypatch.setattr(discover.subprocess, "run", _fake_run_factory(lsof_out))

    services = discover._scan_localhost(public_host="mac.example.ts.net")

    assert len(services) == 1
    assert services[0].get("loopback_only") is True
