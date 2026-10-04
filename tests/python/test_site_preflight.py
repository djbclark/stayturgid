"""Unit tests for control/lib/site_preflight.py — pre-deploy site-sync + vector activation."""

import pytest

from control.lib import site_preflight as sp

VECTOR_PLAN_EXISTING = """vector: mode=own (source=default)
  skip     /h/.config/s/vector/vector.yaml  own-mode base vector.yaml (via ansible role)
  skip     /h/Library/LaunchAgents/com.s.vector.plist  launchd plist com.s.vector
  ansible  serverapp_vector  brew (if absent) + validate + bootstrap + health
"""
VECTOR_PLAN_FIRST = """vector: mode=own (source=default)
  create   /h/.config/s/vector/vector.yaml  own-mode base vector.yaml (via ansible role)
  create   /h/Library/LaunchAgents/com.s.vector.plist  launchd plist com.s.vector
  ansible  serverapp_vector  brew (if absent) + validate + bootstrap + health
"""


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site-example"
    generated = root / "generated" / "stayturgid"
    (generated / "fragments" / "vector").mkdir(parents=True)
    (generated / ".lockfile.yml").write_text("product_commit: aaa\n")
    (generated / "fragments" / "vector" / "stayturgid_sources.yaml").write_text("sources: {}\n")
    return root


@pytest.fixture
def product(tmp_path):
    root = tmp_path / "stayturgid"
    root.mkdir()
    return root


def _fake_recipes(monkeypatch, site, *, sync_writes=None, sync_rc=0, plan=VECTOR_PLAN_EXISTING, vector_rc=0):
    """Replace _run_recipe; site-sync applies ``sync_writes`` to generated/."""
    calls = []

    def run(recipe, site_dir, repo_root, env, *args, capture=False):
        calls.append((recipe, args))
        if recipe == "site-sync" and "mode=dry-run" not in args:
            for rel, text in (sync_writes or {}).items():
                (site / "generated" / "stayturgid" / rel).write_text(text)
            return sync_rc, ""
        if recipe == "site-serverapps" and "mode=dry-run" in args:
            return 0, plan
        if recipe == "site-serverapps":
            return vector_rc, ""
        return 0, ""

    monkeypatch.setattr(sp, "_run_recipe", run)
    return calls


def test_should_skip_honours_env(site, product):
    assert sp.should_skip(site, product, {sp.SKIP_ENV: "1"}) == f"{sp.SKIP_ENV}=1"
    assert sp.should_skip(site, product, {}) is None


def test_should_skip_config_inside_product(product):
    assert "inside the product checkout" in sp.should_skip(product / "ansible", product, {})


def test_content_changes_ignores_lockfile_restamp():
    before = {".lockfile.yml": "a", "inventory/group_vars/all.yml": "x"}
    after = {".lockfile.yml": "b", "inventory/group_vars/all.yml": "x"}
    changed = sp.changed_paths(before, after)
    assert changed == [".lockfile.yml"]
    assert sp.content_changes(changed) == []


def test_changed_paths_includes_created_and_deleted():
    assert sp.changed_paths({"gone.yml": "a"}, {"new.yml": "b"}) == ["gone.yml", "new.yml"]


def test_generated_digest_missing_dir(tmp_path):
    assert sp.generated_digest(tmp_path) == {}


def test_first_vector_activation_detected_from_plan():
    assert sp.is_first_vector_activation(VECTOR_PLAN_FIRST)
    assert not sp.is_first_vector_activation(VECTOR_PLAN_EXISTING)


def test_apply_noop_sync_activates_vector(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site)
    sp.apply(site, product, {}, activate_vector=True)
    assert calls == [
        ("site-sync", ()),
        ("site-serverapps", ("mode=dry-run", "apps=vector")),
        ("site-serverapps", ("apps=vector",)),
    ]


def test_apply_lockfile_only_restamp_proceeds(monkeypatch, site, product, capsys):
    _fake_recipes(monkeypatch, site, sync_writes={".lockfile.yml": "product_commit: bbb\n"})
    sp.apply(site, product, {}, activate_vector=True)
    assert "restamped" in capsys.readouterr().err


def test_apply_content_change_activates_vector_and_continues(monkeypatch, site, product, capsys):
    calls = _fake_recipes(
        monkeypatch,
        site,
        sync_writes={
            ".lockfile.yml": "product_commit: bbb\n",
            "fragments/vector/stayturgid_sources.yaml": "sources: {new: {}}\n",
        },
    )
    sp.apply(site, product, {}, activate_vector=True)
    message = capsys.readouterr().err
    assert "stayturgid_sources.yaml" in message
    assert "Commit them" in message
    assert f"git -C {site} add generated/stayturgid" in message
    assert ("site-serverapps", ("apps=vector",)) in calls


def test_apply_sync_failure_stops_before_vector(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site, sync_rc=2)
    with pytest.raises(sp.SitePreflightError) as excinfo:
        sp.apply(site, product, {}, activate_vector=True)
    assert excinfo.value.exit_code == 2
    assert calls == [("site-sync", ())]


def test_apply_vector_failure_is_reported(monkeypatch, site, product):
    _fake_recipes(monkeypatch, site, vector_rc=1)
    with pytest.raises(sp.SitePreflightError) as excinfo:
        sp.apply(site, product, {}, activate_vector=True)
    assert excinfo.value.exit_code == 1
    assert "vector validate" in str(excinfo.value)


def test_apply_never_first_activates_vector(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, plan=VECTOR_PLAN_FIRST)
    sp.apply(site, product, {}, activate_vector=True)
    assert ("site-serverapps", ("apps=vector",)) not in calls
    assert "never been activated" in capsys.readouterr().err


def test_apply_without_vector_only_syncs(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site)
    sp.apply(site, product, {}, activate_vector=False)
    assert calls == [("site-sync", ())]


def test_apply_skip_env_runs_nothing(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site)
    sp.apply(site, product, {sp.SKIP_ENV: "1"}, activate_vector=True)
    assert calls == []


def test_preview_only_runs_dry_runs(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site)
    assert sp.preview(site, product, {}, activate_vector=True) == 0
    assert calls == [
        ("site-sync", ("mode=dry-run",)),
        ("site-serverapps", ("mode=dry-run", "apps=vector")),
    ]


def test_preview_reports_sync_refusal(monkeypatch, site, product, capsys):
    def run(recipe, site_dir, repo_root, env, *args, capture=False):
        return (2, "") if recipe == "site-sync" else (0, "")

    monkeypatch.setattr(sp, "_run_recipe", run)
    assert sp.preview(site, product, {}, activate_vector=True) == 2
    assert "a real deploy would stop here" in capsys.readouterr().err


def test_run_recipe_invokes_product_justfile_with_site_dir(monkeypatch, site, product):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)

        class R:
            returncode = 0
            stdout = "plan\n"
            stderr = ""

        return R()

    monkeypatch.setattr(sp.shutil, "which", lambda name, path=None: "/opt/homebrew/bin/just")
    monkeypatch.setattr(sp.subprocess, "run", fake_run)
    rc, out = sp._run_recipe("site-serverapps", site, product, {"PATH": "/bin"}, "apps=vector", capture=True)
    assert (rc, out) == (0, "plan\n")
    assert seen["cmd"] == [
        "/opt/homebrew/bin/just",
        "--justfile",
        str(product / "justfile"),
        "site-serverapps",
        f"dir={site}",
        "apps=vector",
    ]
    assert seen["env"]["STAYTURGID_SITE_DIR"] == str(site)
    assert seen["cwd"] == product
    assert seen["timeout"] == sp.PREFLIGHT_TIMEOUT_SECONDS


def test_run_recipe_timeout_returns_124(monkeypatch, site, product):
    import subprocess

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(sp.shutil, "which", lambda name, path=None: "/opt/homebrew/bin/just")
    monkeypatch.setattr(sp.subprocess, "run", fake_run)
    rc, _ = sp._run_recipe("site-sync", site, product, {})
    assert rc == 124


def test_run_recipe_without_just_is_a_clear_error(monkeypatch, site, product):
    monkeypatch.setattr(sp.shutil, "which", lambda name, path=None: None)
    with pytest.raises(sp.SitePreflightError, match="just not found"):
        sp._run_recipe("site-sync", site, product, {})


def test_digest_tracks_real_file_changes(site):
    before = sp.generated_digest(site)
    (site / "generated" / "stayturgid" / "fragments" / "vector" / "stayturgid_sources.yaml").write_text("x\n")
    after = sp.generated_digest(site)
    assert sp.changed_paths(before, after) == ["fragments/vector/stayturgid_sources.yaml"]
