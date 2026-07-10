"""Unit tests for control/bin/deploy_fleet.py — site.yml argv building and deploy wrapper."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "bin"))
import deploy_fleet as df  # noqa: E402


INVENTORY_JSON = {
    "stayturgid": {
        "hosts": {"s24": {}, "hd8": {}, "p7a": {}},
    }
}


def test_parse_inventory_hosts():
    assert df.parse_inventory_hosts(INVENTORY_JSON) == ["s24", "hd8", "p7a"]


def test_run_playbook_argv_full(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["s24", "hd8"], check=False, tags=None)
    assert seen[0] == [
        "ansible-playbook",
        str(df.SITE_PLAYBOOK),
        "--limit",
        "s24,hd8",
    ]


def test_run_playbook_argv_skip_tags(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["s24"], check=False, tags=None, skip_tags="bootstrap")
    assert seen[0][-2:] == ["--skip-tags", "bootstrap"]


def test_run_playbook_argv_check_and_tags(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(df.subprocess, "run", fake_run)
    df.run_playbook(df.SITE_PLAYBOOK, limit=["s24"], check=True, tags="app-stores")
    assert seen[0] == [
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


def _stub_deploy_deps(monkeypatch, calls, *, playbook_rc=0):
    monkeypatch.setattr(df, "require_ansible", lambda: None)
    monkeypatch.setattr(df, "warn_prerequisites", lambda scope: None)
    monkeypatch.setattr(df, "install_collections", lambda: None)

    def run_playbook(playbook, *, limit=None, check, tags, skip_tags=None, extra_vars=None):
        calls.append(("playbook", tags, check, skip_tags))
        return playbook_rc

    monkeypatch.setattr(df, "run_playbook", run_playbook)


def test_deploy_skips_bootstrap_tag(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=False)
    assert rc == 0
    assert calls == [
        ("playbook", None, False, "bootstrap"),
        ("playbook", "mac", False, None),
    ]


def test_deploy_always_runs_mac_even_without_host_limit(monkeypatch):
    """Full-fleet path uses device --limit; Mac must still refresh (L8)."""
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    monkeypatch.setattr(df, "resolve_hosts", lambda hosts: ["s24", "p7a", "hd8"])
    rc = df.deploy(df.Scope.FULL, [], check=False)
    assert rc == 0
    assert ("playbook", "mac", False, None) in calls
    assert calls[-1] == ("playbook", "mac", False, None)


def test_deploy_check_does_not_skip_bootstrap_tag(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=True)
    assert rc == 0
    assert calls == [
        ("playbook", None, True, None),
        ("playbook", "mac", True, None),
    ]


def test_deploy_playbook_failure(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls, playbook_rc=2)
    rc = df.deploy(df.Scope.FULL, ["s24"], check=False)
    assert rc == 2
    assert calls == [
        ("playbook", None, False, "bootstrap"),
        ("playbook", "mac", False, None),
    ]


def test_deploy_check_skips_bootstrap(monkeypatch):
    calls = []
    _stub_deploy_deps(monkeypatch, calls)
    rc = df.deploy(df.Scope.FDROID, ["s24"], check=True)
    assert rc == 0
    assert calls == [
        ("playbook", "fdroid", True, None),
        ("playbook", "mac", True, None),
    ]


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
    env = df.repo_env()
    assert env["ANSIBLE_CONFIG"] == str(df.ANSIBLE_CFG)

