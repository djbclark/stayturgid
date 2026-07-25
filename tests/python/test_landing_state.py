"""Tests for the landing catalog/runtime-state split."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.landing import discover, state


def test_first_use_migrates_legacy_observations(tmp_path, monkeypatch):
    catalog = tmp_path / "services.json"
    runtime = tmp_path / "config" / "services.json"
    catalog.write_text(
        json.dumps({"hidden": [], "services": [{"url": "http://example", "label": "Example", "group": "mac"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(state, "CATALOG_FILE", catalog)
    monkeypatch.setattr(state, "STATE_FILE", runtime)

    migrated = state.load_state()

    assert migrated["services"][0]["url"] == "http://example"
    assert json.loads(runtime.read_text(encoding="utf-8")) == migrated
    assert json.loads(catalog.read_text(encoding="utf-8"))["services"][0].keys() == {"url", "label", "group"}


def test_discovery_writes_runtime_state_not_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "services.json"
    runtime = tmp_path / "config" / "services.json"
    catalog.write_text(
        json.dumps({"hidden": [], "services": [{"url": "http://example", "label": "Example", "group": "mac"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(state, "CATALOG_FILE", catalog)
    monkeypatch.setattr(state, "STATE_FILE", runtime)
    monkeypatch.setattr(discover, "KNOWN_SERVICES", state.load_catalog()["services"])
    monkeypatch.setattr(discover, "_scan_localhost", lambda **_kwargs: [])
    monkeypatch.setattr(discover, "_http_probe", lambda _url: 200)

    before = catalog.read_text(encoding="utf-8")
    result = discover.discover()

    assert result["services"][0]["status_code"] == 200
    assert catalog.read_text(encoding="utf-8") == before
    assert runtime.is_file()


def test_load_registered_ports_from_registry(tmp_path: Path) -> None:
    reg = tmp_path / "registry" / "ports.yml"
    reg.parent.mkdir(parents=True)
    reg.write_text(
        "hosts:\n"
        "  m1-air:\n"
        "    ports:\n"
        "      - {port: 8088, service: landing}\n"
        "      - {port: 8080, service: caddy-health}\n",
        encoding="utf-8",
    )
    ports = discover.load_registered_ports(reg)
    assert ports == {8088, 8080}


def test_scan_localhost_badges_unregistered(monkeypatch) -> None:
    """Registry drift: listeners not in registry get unregistered badge."""

    def fake_lsof(*_a, **_k):
        class R:
            stdout = (
                "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
                "Python  1 user 3u IPv4 0x1 0t0 TCP 127.0.0.1:9999 (LISTEN)\n"
                "Python  2 user 3u IPv4 0x2 0t0 TCP 127.0.0.1:8088 (LISTEN)\n"
            )

        return R()

    monkeypatch.setattr(discover.subprocess, "run", fake_lsof)
    monkeypatch.setattr(discover, "_http_probe", lambda _url, timeout=2.0: 200)
    found = discover._scan_localhost(registered_ports={8088})
    by_port = {s["url"]: s for s in found}
    assert by_port["http://localhost:9999"].get("unregistered") is True
    assert "[unregistered]" in by_port["http://localhost:9999"]["label"]
    assert by_port["http://localhost:8088"].get("unregistered") is not True


def test_discover_prunes_unreachable_unregistered_ports(tmp_path, monkeypatch):
    catalog = tmp_path / "services.json"
    runtime = tmp_path / "config" / "services.json"
    catalog.write_text(
        json.dumps({"hidden": [], "services": [{"url": "http://localhost:8088", "label": "Static", "group": "mac"}]}),
        encoding="utf-8",
    )
    # Pre-populate state with a dead dynamic port (e.g. 52048) and a static port (8088)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        json.dumps(
            {
                "hidden": [],
                "services": [
                    {"url": "http://localhost:8088", "label": "Static", "group": "mac", "reachable": True},
                    {
                        "url": "http://localhost:52048",
                        "label": "Port 52048 [unregistered]",
                        "group": "mac",
                        "unregistered": True,
                        "reachable": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(state, "CATALOG_FILE", catalog)
    monkeypatch.setattr(state, "STATE_FILE", runtime)
    monkeypatch.setattr(discover, "_scan_localhost", lambda **_kwargs: [])
    # Probe fails for all ports
    monkeypatch.setattr(discover, "_http_probe", lambda _url, **_kwargs: None)
    monkeypatch.setattr(discover, "_tcp_probe", lambda _h, _p: False)

    res = discover.discover()
    urls = {s["url"] for s in res["services"]}

    # Static service remains (with reachable=False), dead unregistered dynamic port is pruned
    assert "http://localhost:8088" in urls
    assert "http://localhost:52048" not in urls
