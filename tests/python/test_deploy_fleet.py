"""Unit tests for control/bin/deploy_fleet.py — site.yml argv building and deploy wrapper."""

import os
import sys
from typing import Any

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "bin")
)
import deploy_fleet as df

INVENTORY_JSON: dict[str, Any] = {
    "stayturgid": {
        "hosts": {"oneui-device": {}, "fireos-device": {}, "stock-android-device": {}},
    }
}


def test_parse_inventory_hosts():
    assert df.parse_inventory_hosts(INVENTORY_JSON) == ["oneui-device", "fireos-device", "stock-android-device"]


def test_run_playbook_argv_full(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["oneui-device", "fireos-device"], check=False, tags=None)
    assert seen[0] == [
        "ansible-playbook",
        str(df.SITE_PLAYBOOK),
        "-e",
        f"stayturgid_repo_root={df.REPO_ROOT}",
        "--limit",
        "oneui-device,fireos-device",
    ]


def test_run_playbook_argv_skip_tags(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["oneui-device"], check=False, tags=None, skip_tags="bootstrap")
    assert seen[0][-2:] == ["--skip-tags", "bootstrap"]


def test_run_playbook_argv_check_and_tags(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["oneui-device"], check=True, tags="app-stores")
    assert seen[0] == [
        "ansible-playbook",
        str(df.SITE_PLAYBOOK),
        "-e",
        f"stayturgid_repo_root={df.REPO_ROOT}",
        "--limit",
        "oneui-device",
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
    assert df.Scope.BOOTSTRAP_APKS.ansible_tags == "bootstrap-apks"


def test_resolve_hosts_explicit():
    assert df.resolve_hosts(["oneui-device"]) == ["oneui-device"]


class _FakeContext:
    def __init__(self, collections_path):
        self.collections_path = collections_path


def _stub_install_collections_context(monkeypatch, tmp_path):
    monkeypatch.setattr(df, "resolve_ansible_context", lambda root: _FakeContext(tmp_path))


def test_install_collections_runs_when_no_stamp(monkeypatch, tmp_path):
    calls = []
    _stub_install_collections_context(monkeypatch, tmp_path)
    monkeypatch.setattr(df.subprocess, "run", lambda *a, **k: calls.append(a))
    df.install_collections()
    assert len(calls) == 1
    assert (tmp_path / ".requirements-hash").read_text().strip() == df._requirements_hash()


def test_install_collections_skips_when_hash_matches_and_installed(monkeypatch, tmp_path):
    calls = []
    _stub_install_collections_context(monkeypatch, tmp_path)
    monkeypatch.setattr(df.subprocess, "run", lambda *a, **k: calls.append(a))
    (tmp_path / "ansible_collections").mkdir()
    (tmp_path / ".requirements-hash").write_text(df._requirements_hash())
    df.install_collections()
    assert calls == []


def test_install_collections_reruns_when_hash_stale(monkeypatch, tmp_path):
    calls = []
    _stub_install_collections_context(monkeypatch, tmp_path)
    monkeypatch.setattr(df.subprocess, "run", lambda *a, **k: calls.append(a))
    (tmp_path / "ansible_collections").mkdir()
    (tmp_path / ".requirements-hash").write_text("stale-hash")
    df.install_collections()
    assert len(calls) == 1
    assert (tmp_path / ".requirements-hash").read_text().strip() == df._requirements_hash()


def test_install_collections_reruns_when_collections_dir_missing(monkeypatch, tmp_path):
    """Hash matching a stamp doesn't matter if the collections were removed."""
    calls = []
    _stub_install_collections_context(monkeypatch, tmp_path)
    monkeypatch.setattr(df.subprocess, "run", lambda *a, **k: calls.append(a))
    (tmp_path / ".requirements-hash").write_text(df._requirements_hash())
    df.install_collections()
    assert len(calls) == 1


def test_resolve_hosts_explicit_offline_not_filtered(monkeypatch):
    """Naming an offline host explicitly is an intentional override (#104)."""

    def fail_inventory_list(*_args, **_kwargs):
        raise AssertionError("inventory_list must not be called when hosts is non-empty")

    monkeypatch.setattr(df, "inventory_list", fail_inventory_list)
    assert df.resolve_hosts(["p7a"]) == ["p7a"]


def test_offline_hosts_filters_by_fleet_status_var():
    data = {
        "_meta": {
            "hostvars": {
                "s24": {},
                "p7a": {"stayturgid_fleet_status": "offline"},
                "hd8": {"stayturgid_fleet_status": "online"},
            }
        }
    }
    assert df.offline_hosts(data, ["s24", "p7a", "hd8"]) == ["p7a"]


def test_resolve_hosts_default_skips_offline(monkeypatch, capsys):
    data = {
        "stayturgid": {"hosts": {"s24": {}, "p7a": {}, "hd8": {}}},
        "_meta": {"hostvars": {"p7a": {"stayturgid_fleet_status": "offline"}}},
    }
    monkeypatch.setattr(df, "inventory_list", lambda group="stayturgid": data)
    assert df.resolve_hosts([]) == ["s24", "hd8"]
    assert "skipping offline host(s) p7a" in capsys.readouterr().err


def test_resolve_hosts_all_offline_returns_empty(monkeypatch):
    data = {
        "stayturgid": {"hosts": {"p7a": {}}},
        "_meta": {"hostvars": {"p7a": {"stayturgid_fleet_status": "offline"}}},
    }
    monkeypatch.setattr(df, "inventory_list", lambda group="stayturgid": data)
    assert df.resolve_hosts([]) == []


def _stub_deploy_deps(monkeypatch, calls, *, playbook_rc=0):
    monkeypatch.setattr(df, "require_ansible", lambda: None)
    monkeypatch.setattr(df, "warn_prerequisites", lambda scope: None)
    monkeypatch.setattr(df, "install_collections", lambda: None)
    monkeypatch.setattr(df, "resolve_ansible_context", lambda root, environ=None: object())
    monkeypatch.setattr(df, "require_inventory", lambda context: None)
    monkeypatch.setattr(df, "require_limit_hosts", lambda context, limit: limit.split(","))

    def run_playbook(playbook, *, limit=None, check, tags, skip_tags=None, extra_vars=None, verbose=0):
        calls.append(("playbook", tags, check, skip_tags))
        return playbook_rc

    monkeypatch.setattr(df, "run_playbook", run_playbook)


def test_deploy_skips_bootstrap_tag(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["oneui-device"], check=False)
    assert rc == 0
    assert calls == [
        ("playbook", None, False, "bootstrap"),
        ("playbook", "mac", False, None),
    ]


def test_deploy_always_runs_mac_even_without_host_limit(monkeypatch):
    """Full-fleet path uses device --limit; Mac must still refresh (L8)."""
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    monkeypatch.setattr(df, "resolve_hosts", lambda hosts: ["oneui-device", "stock-android-device", "fireos-device"])
    rc = df.deploy(df.Scope.FULL, [], check=False)
    assert rc == 0
    assert ("playbook", "mac", False, None) in calls
    assert calls[-1] == ("playbook", "mac", False, None)


def test_deploy_devices_only_skips_mac_pass(monkeypatch):
    """#57: --devices-only must not launch the second control_node/site.yml pass."""
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["oneui-device"], check=False, devices_only=True)
    assert rc == 0
    assert calls == [
        ("playbook", None, False, "bootstrap"),
    ]


def test_deploy_devices_only_still_reports_device_playbook_failure(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls, playbook_rc=2)
    rc = df.deploy(df.Scope.FULL, ["oneui-device"], check=False, devices_only=True)
    assert rc == 2
    assert calls == [
        ("playbook", None, False, "bootstrap"),
    ]


def test_deploy_check_skips_mutating_bootstrap_tag(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["oneui-device"], check=True)
    assert rc == 0
    assert calls == [
        ("playbook", None, True, "bootstrap"),
    ]


def test_deploy_playbook_failure(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls, playbook_rc=2)
    rc = df.deploy(df.Scope.FULL, ["oneui-device"], check=False)
    assert rc == 2
    assert calls == [
        ("playbook", None, False, "bootstrap"),
        ("playbook", "mac", False, None),
    ]


def test_deploy_check_skips_bootstrap(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FDROID, ["oneui-device"], check=True)
    assert rc == 0
    assert calls == [
        ("playbook", "fdroid", True, "bootstrap"),
    ]


def test_deploy_all_hosts_offline_refuses_not_all_fallback(monkeypatch, capsys):
    """An empty limit string falls back to 'all' in require_limit_hosts — must
    never reach there when every host is offline (#104)."""
    calls = []
    _stub_deploy_deps(monkeypatch, calls)

    def fail_require_limit_hosts(*_args, **_kwargs):
        raise AssertionError("require_limit_hosts must not be called with zero targets")

    monkeypatch.setattr(df, "require_limit_hosts", fail_require_limit_hosts)
    monkeypatch.setattr(df, "resolve_hosts", lambda hosts: [])
    rc = df.deploy(df.Scope.FULL, [], check=False)
    assert rc == 1
    assert calls == []
    assert "every fleet host is marked offline" in capsys.readouterr().err


def test_run_playbook_timeout_returns_124(monkeypatch):
    import subprocess as sp

    def fake_run(cmd, **kwargs):
        raise sp.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    rc = df.run_playbook(df.SITE_PLAYBOOK, limit=["oneui-device"], check=False, tags=None)
    assert rc == 124


def test_run_playbook_passes_configured_timeout(monkeypatch):
    seen_kwargs = {}

    def fake_run(cmd, **kwargs):
        seen_kwargs.update(kwargs)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["oneui-device"], check=False, tags=None)
    assert seen_kwargs["timeout"] == df.DEPLOY_TIMEOUT_SECONDS


def test_deploy_blocks_concurrent_run(monkeypatch):
    """A deploy already holding the fleet lock must block a second one (#58)."""
    calls = []
    _stub_deploy_deps(monkeypatch, calls)

    with df.fleet_lock("deploy_fleet.py s24"):
        with pytest.raises(df.FleetLockHeld):
            df.deploy(df.Scope.FULL, ["oneui-device"], check=False)
    assert calls == []


def test_main_passes_devices_only_flag(monkeypatch):
    seen = {}

    def fake_deploy(scope, hosts, *, check, verbose=0, devices_only=False):
        seen["devices_only"] = devices_only
        return 0

    monkeypatch.setattr(df, "deploy", fake_deploy)
    rc = df.main(["--devices-only", "oneui-device"])
    assert rc == 0
    assert seen["devices_only"] is True


def test_main_defaults_devices_only_false(monkeypatch):
    seen = {}

    def fake_deploy(scope, hosts, *, check, verbose=0, devices_only=False):
        seen["devices_only"] = devices_only
        return 0

    monkeypatch.setattr(df, "deploy", fake_deploy)
    rc = df.main(["oneui-device"])
    assert rc == 0
    assert seen["devices_only"] is False


def test_main_reports_lock_conflict_with_exit_code_3(monkeypatch):
    def raise_held(*_args, **_kwargs):
        raise df.FleetLockHeld("another fleet-touching script is already running: x (pid 1, started now)")

    monkeypatch.setattr(df, "deploy", raise_held)
    rc = df.main(["oneui-device"])
    assert rc == 3


def test_load_play_env_merges_missing_keys(tmp_path, monkeypatch):
    play_env = tmp_path / "play.env"
    play_env.write_text(
        "export GPLAY_EMAIL='a@b.com'\n"
        "export GPLAY_AAS_TOKEN='aas_et/test'\n"
        "# comment\n"
        "GPLAY_AUTH_TOKEN=ignored_if_set\n"
    )
    monkeypatch.setattr(df.Path, "home", classmethod(lambda cls: tmp_path.parent))
    # Point load_play_env at our file by patching Path.home()/.config/...
    # Simpler: call with a custom path via monkeypatch of Path.home structure
    cfg = tmp_path / ".config" / "stayturgid"
    cfg.mkdir(parents=True)
    (cfg / "play.env").write_text(play_env.read_text())
    monkeypatch.setattr(df.Path, "home", classmethod(lambda cls, _t=tmp_path: _t))

    env = {"GPLAY_AUTH_TOKEN": "keep-me", "PATH": "/bin"}
    df.load_play_env(env)
    assert env["GPLAY_EMAIL"] == "a@b.com"
    assert env["GPLAY_AAS_TOKEN"] == "aas_et/test"
    assert env["GPLAY_AUTH_TOKEN"] == "keep-me"  # existing wins


def test_load_play_env_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(df.Path, "home", classmethod(lambda cls, _t=tmp_path: _t))
    env = {"PATH": "/bin"}
    df.load_play_env(env)
    assert env == {"PATH": "/bin"}


def test_repo_env_includes_ansible_config(monkeypatch, tmp_path):
    monkeypatch.setattr(df.Path, "home", classmethod(lambda cls, _t=tmp_path: _t))
    monkeypatch.delenv("GPLAY_EMAIL", raising=False)
    site = tmp_path / "site-example"
    (site / "inventory").mkdir(parents=True)
    (site / "ansible.cfg").write_text("[defaults]\ninventory = inventory/hosts.yml\n", encoding="utf-8")
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")
    monkeypatch.setenv("ANSIBLE_CONFIG", str(site / "ansible.cfg"))
    env = df.repo_env()
    assert env["ANSIBLE_CONFIG"] == str(site / "ansible.cfg")
    assert env["STAYTURGID_ROOT"] == str(df.REPO_ROOT)


def test_repo_env_fails_without_any_site_selection(monkeypatch, tmp_path):
    """§4.8: zero discovered site-* checkouts must not silently default."""
    monkeypatch.setattr(df.Path, "home", classmethod(lambda cls, _t=tmp_path: _t))
    monkeypatch.delenv("ANSIBLE_CONFIG", raising=False)
    monkeypatch.delenv("STAYTURGID_SITE_DIR", raising=False)
    monkeypatch.setenv("OPS_ROOT", str(tmp_path / "empty-ops"))
    import pytest

    from control.lib.ansible_context import AnsibleConfigError

    with pytest.raises(AnsibleConfigError, match="ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite"):
        df.repo_env()
