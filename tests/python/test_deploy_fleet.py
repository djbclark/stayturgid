"""Unit tests for mac/deploy_fleet.py — site.yml argv building and deploy wrapper."""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mac"))
import deploy_fleet as df  # noqa: E402


INVENTORY_JSON = {
    "stayturgid": {
        "hosts": {"s24": {}, "hd8": {}, "p7a": {}},
    }
}


def test_parse_inventory_hosts():
    assert df.parse_inventory_hosts(INVENTORY_JSON) == ["s24", "hd8", "p7a"]


def test_build_playbook_argv_full():
    cmd = df.build_playbook_argv(limit=["s24", "hd8"], check=False, tags=None)
    assert cmd == [
        "ansible-playbook",
        str(df.SITE_PLAYBOOK),
        "--limit",
        "s24,hd8",
    ]


def test_build_playbook_argv_check_and_tags():
    cmd = df.build_playbook_argv(limit=["s24"], check=True, tags="app-stores")
    assert cmd == [
        "ansible-playbook",
        str(df.SITE_PLAYBOOK),
        "--limit",
        "s24",
        "--check",
        "--diff",
        "--tags",
        "app-stores",
    ]


def test_check_mode_env(monkeypatch):
    monkeypatch.delenv("CHECK", raising=False)
    assert df.check_mode(False) is False
    monkeypatch.setenv("CHECK", "1")
    assert df.check_mode(False) is True
    assert df.check_mode(True) is True


def test_scope_ansible_tags():
    assert df.Scope.FULL.ansible_tags is None
    assert df.Scope.FDROID.ansible_tags == "fdroid"
    assert df.Scope.PLAY.ansible_tags == "play,post-ui"
    assert df.Scope.APP_STORES.ansible_tags == "app-stores"


def test_resolve_hosts_explicit():
    assert df.resolve_hosts(["s24"]) == ["s24"]


def _stub_deploy_deps(monkeypatch, calls, *, playbook_rc=0, bootstrap_rc=0):
    monkeypatch.setattr(df, "require_ansible", lambda: None)
    monkeypatch.setattr(df, "warn_prerequisites", lambda scope: None)
    monkeypatch.setattr(df, "install_collections", lambda: None)

    def ensure_ssh_bootstrap(hosts):
        calls.append(("bootstrap", list(hosts)))
        return bootstrap_rc

    def run_playbook(*, limit, check, tags):
        calls.append(("playbook", tags, check))
        return playbook_rc

    monkeypatch.setattr(df, "ensure_ssh_bootstrap", ensure_ssh_bootstrap)
    monkeypatch.setattr(df, "run_playbook", run_playbook)


def test_deploy_runs_site_playbook(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=False)
    assert rc == 0
    assert calls == [
        ("bootstrap", ["s24"]),
        ("playbook", None, False),
    ]


def test_deploy_playbook_failure(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls, playbook_rc=2)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=False)
    assert rc == 2
    assert calls == [
        ("bootstrap", ["s24"]),
        ("playbook", None, False),
    ]


def test_deploy_check_skips_bootstrap(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FDROID, ["s24"], check=True)
    assert rc == 0
    assert calls == [("playbook", "fdroid", True)]


def test_deploy_bootstrap_failure_short_circuits(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls, bootstrap_rc=1)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=False)
    assert rc == 1
    assert calls == [("bootstrap", ["s24"])]
