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
