"""Regression tests for the native-agent peer provisioning helper."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

MODULE_PATH = Path(__file__).resolve().parents[2] / "control" / "tools" / "native-agent" / "provision_peer.py"
SPEC = importlib.util.spec_from_file_location("provision_peer", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
provision_peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision_peer)


def test_default_package_resolution_deduplicates_release_probe(monkeypatch):
    seen = []

    def installed(_serial, package):
        seen.append(package)
        return package == provision_peer.DEBUG_PKG

    monkeypatch.setattr(provision_peer, "PKG_OVERRIDE", None)
    monkeypatch.setattr(provision_peer.adb, "package_installed", installed)

    assert provision_peer._resolve_pkg("device") == provision_peer.DEBUG_PKG
    assert seen == [provision_peer.DEFAULT_PKG, provision_peer.DEBUG_PKG]


def test_explicit_package_override_does_not_fall_through(monkeypatch):
    seen = []

    def installed(_serial, package):
        seen.append(package)
        return package == provision_peer.DEFAULT_PKG

    monkeypatch.setattr(provision_peer, "PKG_OVERRIDE", "com.example.agent")
    monkeypatch.setattr(provision_peer, "PKG", "com.example.agent")
    monkeypatch.setattr(provision_peer.adb, "package_installed", installed)

    assert provision_peer._resolve_pkg("device") is None
    assert seen == ["com.example.agent"]


def test_set_target_reminder_uses_mac_adb_transport_not_peer_tailscale_ip(monkeypatch):
    """#66: the Mac is frequently USB-only for a target whose peer reaches it over
    Tailscale — set_target_reminder must reverse-resolve to the Mac's own adb
    transport (USB serial here) for the shell commands, not the raw peer-facing
    Tailscale host:port, and must not `adb connect` a USB serial."""
    monkeypatch.setattr(provision_peer.adb, "alias_for_host", lambda host: "hd8" if host == "100.124.55.39" else None)
    monkeypatch.setattr(provision_peer.adb, "resolve_target", lambda alias: "USBSERIAL123" if alias == "hd8" else alias)
    connect_calls = []
    monkeypatch.setattr(provision_peer.adb, "run", lambda cmd, **kw: connect_calls.append(cmd))
    shell_targets = []

    def fake_adb(serial, *args, **kwargs):
        shell_targets.append(serial)
        return Mock(stdout="OK")

    monkeypatch.setattr(provision_peer.adb, "adb", fake_adb)

    provision_peer.set_target_reminder("100.124.55.39:5555")

    assert connect_calls == []  # USB serial never needs `adb connect`
    assert shell_targets == ["USBSERIAL123", "USBSERIAL123"]  # one per AGENT_PKGS entry


def test_set_target_reminder_falls_back_to_raw_target_when_host_unknown(monkeypatch):
    """A target not in devices.conf (no reverse-lookup alias) still gets a
    best-effort `adb connect` + shell against the raw host:port, matching the
    pre-existing behavior for ad-hoc targets."""
    monkeypatch.setattr(provision_peer.adb, "alias_for_host", lambda host: None)
    monkeypatch.setattr(provision_peer.adb, "resolve_target", lambda alias: alias)
    connect_calls = []
    monkeypatch.setattr(provision_peer.adb, "run", lambda cmd, **kw: connect_calls.append(cmd))
    shell_targets = []

    def fake_adb(serial, *args, **kwargs):
        shell_targets.append(serial)
        return Mock(stdout="OK")

    monkeypatch.setattr(provision_peer.adb, "adb", fake_adb)

    provision_peer.set_target_reminder("203.0.113.5:5555")

    assert connect_calls and connect_calls[0][-1] == "203.0.113.5:5555"
    assert shell_targets == ["203.0.113.5:5555", "203.0.113.5:5555"]
