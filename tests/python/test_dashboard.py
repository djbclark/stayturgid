"""Dashboard H8 tests; no device or network access required."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))

pytest.importorskip("flask")
import dashboard  # noqa: E402


def test_rish_probe_requires_uid_2000(monkeypatch):
    class Result:
        returncode = 0
        stdout = "1000\n"
        stderr = ""

    monkeypatch.setattr(dashboard, "resolve_ssh_host", lambda _host: "s24")
    monkeypatch.setattr(dashboard.subprocess, "run", lambda *a, **k: Result())
    ok, message = dashboard._rish_probe("s24")
    assert not ok
    assert "not authorized" in message


def test_request_shizuku_opens_app_then_reports_uid_2000(monkeypatch):
    class Shell:
        def sh(self, command, timeout=20):
            assert "moe.shizuku.privileged.api" in command
            return 0, "Starting: Intent { ... }"

    monkeypatch.setattr(dashboard, "PrivShell", lambda _host: Shell())
    monkeypatch.setattr(dashboard, "_rish_probe", lambda _host: (True, "authorized (UID 2000)"))
    assert dashboard.request_shizuku_authorization("s24") == (True, "authorized (UID 2000)")


def test_shizuku_route_rejects_unknown_host(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 - 1.2.3.4 - S24\n")
    monkeypatch.setattr(dashboard, "DEVICES_CONF", conf)
    response = dashboard.app.test_client().post("/api/shizuku/unknown")
    assert response.status_code == 404
