"""Regression tests for the native-agent peer provisioning helper."""

import importlib.util
from pathlib import Path

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
