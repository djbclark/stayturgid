"""Unit tests for control/lib/site_preflight.py — pre-deploy site-sync + vector activation."""

import os
import shutil
import subprocess

import pytest

from control.lib import site_preflight as sp

REAL_GIT = sp._git

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


@pytest.fixture(autouse=True)
def no_real_git(monkeypatch):
    """Tests that do not opt in see a site that is not a git checkout."""
    monkeypatch.setattr(sp, "_git", lambda cwd, env, *args: (128, "fatal: not a git repository"))


class FakeGit:
    """Stand-in for sp._git: a site checkout whose committed generated/ is the fixture's content."""

    def __init__(self, site, calls, *, detached=False, in_progress=None, fail=None):
        self.site = site
        self.calls = calls
        self.committed = sp.generated_digest(site)
        self.git_dir = site / ".git"
        self.git_dir.mkdir(exist_ok=True)
        if in_progress:
            (self.git_dir / in_progress).mkdir()
        self.detached = detached
        self.fail = fail or {}

    def __call__(self, cwd, env, *args):
        self.calls.append(("git", args))
        if args[0] in self.fail:
            return self.fail[args[0]], f"{args[0]} rejected"
        if args[:2] == ("rev-parse", "--short"):
            return 0, "abc1234\n"
        if args == ("rev-parse", "--absolute-git-dir"):
            return 0, f"{self.git_dir}\n"
        if args[0] == "symbolic-ref":
            return (1, "") if self.detached else (0, "refs/heads/master\n")
        if args[0] == "status":
            changed = sp.changed_paths(self.committed, sp.generated_digest(self.site))
            return 0, "".join(f" M generated/stayturgid/{path}\n" for path in changed)
        return 0, ""


def _fake_git(monkeypatch, site, calls, **kwargs):
    fake = FakeGit(site, calls, **kwargs)
    monkeypatch.setattr(sp, "_git", fake)
    return fake


def _git_writes(calls):
    return [args for kind, args in calls if kind == "git" and args[0] in ("add", "commit", "push")]


LOCKFILE_RESTAMP = {".lockfile.yml": "product_commit: bbb\n"}
CONTENT_CHANGE = {**LOCKFILE_RESTAMP, "fragments/vector/stayturgid_sources.yaml": "sources: {new: {}}\n"}
EXPECTED_WRITES = [
    ("add", "--", "generated/stayturgid"),
    ("commit", "-m", "chore(generated): sync from stayturgid abc1234", "--", "generated/stayturgid"),
    ("push",),
]


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
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    sp.apply(site, product, {}, activate_vector=True)
    message = capsys.readouterr().err
    assert "stayturgid_sources.yaml" in message
    assert "not committing generated/stayturgid" in message
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


def test_autocommit_nothing_changed_writes_nothing(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site)
    _fake_git(monkeypatch, site, calls)
    sp.apply(site, product, {}, activate_vector=True)
    assert ("git", ("status", "--porcelain", "--", "generated/stayturgid")) in calls
    assert _git_writes(calls) == []


def test_autocommit_lockfile_only_restamp_is_committed(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, sync_writes=LOCKFILE_RESTAMP)
    _fake_git(monkeypatch, site, calls)
    sp.apply(site, product, {}, activate_vector=True)
    assert _git_writes(calls) == EXPECTED_WRITES
    assert "pushed" in capsys.readouterr().err


def test_autocommit_content_change_commits_after_vector(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    _fake_git(monkeypatch, site, calls)
    sp.apply(site, product, {}, activate_vector=True)
    assert _git_writes(calls) == EXPECTED_WRITES
    assert calls.index(("site-serverapps", ("apps=vector",))) < calls.index(("git", EXPECTED_WRITES[0]))
    message = capsys.readouterr().err
    assert "stayturgid_sources.yaml" in message
    assert "committed 2 path(s)" in message


def test_autocommit_vector_failure_commits_nothing(monkeypatch, site, product):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE, vector_rc=1)
    _fake_git(monkeypatch, site, calls)
    with pytest.raises(sp.SitePreflightError):
        sp.apply(site, product, {}, activate_vector=True)
    assert _git_writes(calls) == []


def test_autocommit_push_failure_warns_and_continues(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    _fake_git(monkeypatch, site, calls, fail={"push": 1})
    sp.apply(site, product, {}, activate_vector=True)
    message = capsys.readouterr().err
    assert "WARNING" in message and "`git push` failed" in message
    assert f"git -C {site} pull --rebase && git -C {site} push" in message


def test_autocommit_commit_failure_warns_with_manual_command(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    _fake_git(monkeypatch, site, calls, fail={"commit": 1})
    sp.apply(site, product, {}, activate_vector=True)
    message = capsys.readouterr().err
    assert "`git commit` failed" in message
    assert f"git -C {site} add -- generated/stayturgid && git -C {site} commit -m" in message
    assert ("push",) not in _git_writes(calls)


def test_autocommit_switch_off_touches_no_git(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    _fake_git(monkeypatch, site, calls)
    sp.apply(site, product, {sp.AUTOCOMMIT_ENV: "0"}, activate_vector=True)
    assert [c for c in calls if c[0] == "git"] == []
    assert f"{sp.AUTOCOMMIT_ENV}=0" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"detached": True}, "detached HEAD"),
        ({"in_progress": "rebase-merge"}, "rebase is in progress"),
        ({"in_progress": "MERGE_HEAD"}, "merge or rebase is in progress"),
    ],
)
def test_autocommit_skips_unsafe_checkout(monkeypatch, site, product, capsys, kwargs, reason):
    calls = _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    _fake_git(monkeypatch, site, calls, **kwargs)
    sp.apply(site, product, {}, activate_vector=True)
    assert _git_writes(calls) == []
    assert reason in capsys.readouterr().err


def test_autocommit_not_a_checkout_is_a_note(monkeypatch, site, product, capsys):
    _fake_recipes(monkeypatch, site, sync_writes=CONTENT_CHANGE)
    sp.apply(site, product, {}, activate_vector=True)
    assert "is not a git checkout" in capsys.readouterr().err


def test_preview_reports_but_never_writes_git(monkeypatch, site, product, capsys):
    calls = _fake_recipes(monkeypatch, site)
    (site / "generated" / "stayturgid" / ".lockfile.yml").write_text("product_commit: left over\n")
    fake = _fake_git(monkeypatch, site, calls)
    fake.committed = {**fake.committed, ".lockfile.yml": "committed"}
    assert sp.preview(site, product, {}, activate_vector=True) == 0
    assert _git_writes(calls) == []
    message = capsys.readouterr().err
    assert "a real deploy commits and pushes" in message
    assert "generated/stayturgid/.lockfile.yml" in message


def test_git_disables_prompts_and_times_out(monkeypatch, site):
    monkeypatch.setattr(sp, "_git", REAL_GIT)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(sp.subprocess, "run", fake_run)
    rc, out = sp._git(site, {"PATH": "/bin"}, "push")
    assert rc == 124 and "git push exceeded" in out
    assert seen["cmd"] == ["git", "-C", str(site), "push"]
    assert seen["env"] == {"PATH": "/bin", "GIT_TERMINAL_PROMPT": "0"}
    assert seen["timeout"] == sp.GIT_TIMEOUT_SECONDS


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_autocommit_real_repo_leaves_unrelated_work_alone(monkeypatch, tmp_path, site, product):
    monkeypatch.setattr(sp, "_git", REAL_GIT)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }

    def git(*args, cwd=site):
        return subprocess.run(
            ["git", "-C", str(cwd), *args], env=env, text=True, capture_output=True, check=True
        ).stdout

    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "master", str(remote), cwd=tmp_path)
    (site / "notes.txt").write_text("v1\n")
    git("init", "-q", "-b", "master")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("remote", "add", "origin", str(remote))
    git("push", "-q", "-u", "origin", "master")
    (site / "notes.txt").write_text("another session's edit\n")
    (site / "staged.txt").write_text("staged by another session\n")
    git("add", "staged.txt")
    (site / "untracked.txt").write_text("scratch\n")

    _fake_recipes(monkeypatch, site, sync_writes={**CONTENT_CHANGE, "new.yml": "new: true\n"})
    sp.apply(site, product, env, activate_vector=True)

    assert git("log", "-1", "--format=%s") == "chore(generated): sync from stayturgid\n"
    assert sorted(git("show", "--name-only", "--format=", "HEAD").split()) == [
        "generated/stayturgid/.lockfile.yml",
        "generated/stayturgid/fragments/vector/stayturgid_sources.yaml",
        "generated/stayturgid/new.yml",
    ]
    assert sorted(git("status", "--porcelain").splitlines()) == [" M notes.txt", "?? untracked.txt", "A  staged.txt"]
    assert git("rev-parse", "HEAD") == git("rev-parse", "master", cwd=remote)
