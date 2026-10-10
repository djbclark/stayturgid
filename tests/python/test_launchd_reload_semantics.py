"""Assert launchd plist-change reload semantics (M1-F MF-3).

launchd caches the loaded plist definition; `kickstart -k` restarts a daemon
with the *old* definition, so a changed plist must go through
bootout-then-bootstrap, not kickstart. kickstart is only correct for
config-only changes.

Since 919ace1 that lifecycle lives once in the shared ``serverapp_launchd``
role, which caddy/grafana/vector/victoriametrics include. openobserve and
olivetin were not converted and still carry their own copies, so they are
checked separately against the same invariant. These tests parse tasks/main.yml
and assert the task shapes rather than running ansible.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = ROOT / "ansible" / "roles"

SHARED_ROLE = "serverapp_launchd"

# Roles that include SHARED_ROLE for their launchd lifecycle.
DELEGATING_ROLES = {"caddy", "grafana", "vector", "victoriametrics"}

# Roles that still carry an inline copy -> its register-variable prefix.
# Converting these is fine; dropping the semantics is not, so they keep their
# own assertions until they move over.
INLINE_ROLES = {
    "openobserve": "_oo",
    "olivetin": "_ot",
    "blackbox_exporter": "_bbe",
}

# Roles with no own-mode config that can change independently of the plist, so
# no config-only change is left for a kickstart to serve. Having no kickstart
# task is the correct shape for these, not a gap.
NO_KICKSTART = {"openobserve", "landing"}

# landing runs two agents off two plists, so its tasks do not fit the
# one-label-per-role shape the helpers above assume; it is asserted separately.
LANDING_AGENTS = {
    "landing": "_landing",
    "landing-discover": "_landing_discover",
}


def _load_tasks(role: str) -> list[dict]:
    return yaml.safe_load((ROLES_DIR / role / "tasks" / "main.yml").read_text(encoding="utf-8"))


def _find(tasks: list[dict], substring: str) -> dict:
    matches = [t for t in tasks if substring in t.get("name", "")]
    assert len(matches) == 1, f"expected exactly one task matching {substring!r}, got {len(matches)}"
    return matches[0]


def _as_text(when) -> str:
    if isinstance(when, list):
        return " ".join(str(w) for w in when)
    return str(when)


# ── the shared lifecycle ──────────────────────────────────────────────────


def test_shared_role_boots_out_on_plist_change() -> None:
    boot = _find(_load_tasks(SHARED_ROLE), "when its launchd plist changed")
    when_text = _as_text(boot["when"])
    assert "loaded" in when_text
    assert "sl_plist_changed" in when_text
    # A bool passed into an included role can arrive as the string "False",
    # which is truthy in Jinja and would invert this guard.
    assert "| bool" in when_text


def test_shared_role_bootstraps_on_unloaded_or_plist_change_with_retries() -> None:
    bootstrap = _find(_load_tasks(SHARED_ROLE), "when unloaded or its plist changed")
    when_text = _as_text(bootstrap["when"])
    assert "unloaded" in when_text
    assert "_sl_plist_reload_bootout.changed" in when_text
    assert bootstrap.get("retries") == 5, f"expected retries: 5, got {bootstrap.get('retries')!r}"
    assert "until" in bootstrap, "bootstrap task missing until (must retry on failure)"


def test_shared_role_kickstart_excluded_on_plist_change() -> None:
    kickstart = _find(_load_tasks(SHARED_ROLE), "Kickstart the site-namespace service")
    when_text = _as_text(kickstart["when"])
    assert "sl_plist_changed" in when_text
    assert "not" in when_text
    assert "| bool" in when_text


# ── roles that still own a copy of it ─────────────────────────────────────


def test_inline_roles_boot_out_on_plist_change() -> None:
    for app, prefix in INLINE_ROLES.items():
        tasks = _load_tasks(f"serverapp_{app}")
        boot = _find(tasks, "when its launchd plist changed")
        when_text = _as_text(boot["when"])
        assert "loaded" in when_text, app
        assert f"{prefix}_plist.changed" in when_text, app


def test_inline_roles_bootstrap_on_unloaded_or_plist_change_with_retries() -> None:
    for app, prefix in INLINE_ROLES.items():
        tasks = _load_tasks(f"serverapp_{app}")
        bootstrap = _find(tasks, "when unloaded or its plist changed")
        when_text = _as_text(bootstrap["when"])
        assert "unloaded" in when_text, app
        assert f"{prefix}_plist_reload_bootout.changed" in when_text, app
        assert bootstrap.get("retries") == 5, f"{app}: expected retries: 5, got {bootstrap.get('retries')!r}"
        assert "until" in bootstrap, f"{app}: bootstrap task missing until (must retry on failure)"


def test_inline_role_kickstart_restricted_to_config_only_change() -> None:
    # openobserve has no own-mode config template that can change independently
    # of the plist, so it has no kickstart task at all — that's correct, not a gap.
    for app, prefix in INLINE_ROLES.items():
        if app in NO_KICKSTART:
            continue
        kickstart = _find(_load_tasks(f"serverapp_{app}"), f"Kickstart site-namespace {app}")
        when_text = _as_text(kickstart["when"])
        assert f"{prefix}_plist.changed" in when_text, app
        assert "not" in when_text, app


def test_landing_boots_out_both_agents_on_plist_change() -> None:
    """landing drives two launchd agents from one role, so it gets its own check.

    It used to kickstart both on a plist change and bootstrap only when
    unloaded — the same drift 919ace1 corrected in victoriametrics.
    """
    tasks = _load_tasks("serverapp_landing")
    for label, prefix in LANDING_AGENTS.items():
        boot = _find(tasks, f"Boot out site-namespace {label} when its launchd plist changed")
        boot_when = _as_text(boot["when"])
        assert "loaded" in boot_when, label
        assert f"{prefix}_plist.changed" in boot_when, label

        bootstrap = _find(tasks, f"Bootstrap site-namespace {label} when unloaded or its plist changed")
        bootstrap_when = _as_text(bootstrap["when"])
        assert "unloaded" in bootstrap_when, label
        assert f"{prefix}_plist_reload_bootout.changed" in bootstrap_when, label
        assert bootstrap.get("retries") == 5, label
        assert "until" in bootstrap, label

    # landing renders no config separately from its plists. Its only kickstarts
    # restart an agent whose *code* changed (#224); each must stay off on a plist
    # change (bootout + bootstrap already reloaded it) and after a bootstrap.
    kickstarts = [t for t in tasks if "Kickstart" in t.get("name", "")]
    assert {t["name"] for t in kickstarts} == {
        f"Kickstart site-namespace {label} when only its code changed" for label in LANDING_AGENTS
    }
    for label, prefix in LANDING_AGENTS.items():
        kick = _find(tasks, f"Kickstart site-namespace {label} when only its code changed")
        when_text = _as_text(kick["when"])
        assert "_landing_code is changed" in when_text, label
        assert f"not ({prefix}_plist.changed" in when_text, label
        assert f"not ({prefix}_bootstrap.changed" in when_text, label


# ── nobody gets to roll their own quietly ─────────────────────────────────


def test_every_serverapp_role_delegates_or_is_a_known_inline_copy() -> None:
    """A new serverapp role must include the shared role, not re-copy it.

    The duplication this guards against is exactly how victoriametrics drifted
    into kickstarting on a plist change (919ace1).
    """
    for role_dir in sorted(ROLES_DIR.glob("serverapp_*")):
        app = role_dir.name.removeprefix("serverapp_")
        if app == "launchd":
            continue  # this *is* the shared lifecycle
        tasks_file = role_dir / "tasks" / "main.yml"
        if not tasks_file.is_file():
            continue
        text = tasks_file.read_text(encoding="utf-8")
        if "launchctl" not in text and SHARED_ROLE not in text:
            continue  # no launchd lifecycle of its own (e.g. a pure config role)
        if app in INLINE_ROLES or app == "landing":
            continue
        assert SHARED_ROLE in text, (
            f"serverapp_{app} manages launchd without including {SHARED_ROLE}. "
            f"Include the shared role, or add it to INLINE_ROLES here with its own assertions."
        )
        assert app in DELEGATING_ROLES, f"serverapp_{app} delegates but is missing from DELEGATING_ROLES"


def test_landing_code_hash_flips_only_on_a_tracked_code_edit(tmp_path: Path) -> None:
    """#224: a code-only change under control/landing/ must be detected.

    Runs the role's hash script verbatim against a scratch git checkout: a
    tracked byte edit flips it to changed, an untracked runtime file does not,
    and recording the printed hash (what the role's copy task does after health
    passes) settles it again.
    """
    import subprocess

    tasks = _load_tasks("serverapp_landing")
    task = _find(tasks, "Hash landing code the agents execute")
    assert task.get("check_mode") is False  # read-only probe, reported by deploy-check
    script = "\n".join(
        line
        for line in task["ansible.builtin.shell"]["cmd"].splitlines()
        if line.strip() not in {"{% raw %}", "{% endraw %}"}
    )
    record = _find(tasks, "Record the landing code hash")
    assert record["when"] == "_landing_code is changed"
    assert tasks.index(record) > tasks.index(_find(tasks, "Wait for landing health endpoint"))

    repo = tmp_path / "repo"
    code = repo / "control" / "landing"
    code.mkdir(parents=True)
    (code / "landing.py").write_text("print('v1')\n")
    (code / "services.json").write_text("{}\n")
    lib = repo / "control" / "lib"
    lib.mkdir()
    (lib / "ansible_context.py").write_text("v1\n")
    (lib / "fleet_targets.py").write_text("v1\n")
    (lib / "unrelated.py").write_text("v1\n")
    git = [
        "git",
        "-C",
        str(repo),
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "v1"], check=True)
    state = tmp_path / "landing-code.sha256"
    env = {
        **os.environ,
        "REPO_ROOT": str(repo),
        "CODE_PATHS": "control/landing control/lib/ansible_context.py control/lib/fleet_targets.py control/lib/site_discovery.py",
        "STATE_FILE": str(state),
    }

    def probe() -> tuple[str, str]:
        out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True)
        digest, verdict = out.stdout.split()
        return digest, verdict

    digest, verdict = probe()
    assert verdict == "changed"  # no recorded hash yet
    state.write_text(digest + "\n")
    assert probe()[1] == "unchanged"
    (code / "__pycache__").mkdir()
    (code / "__pycache__" / "x.pyc").write_bytes(b"junk")
    assert probe()[1] == "unchanged"  # runtime junk is not code
    (code / "landing.py").write_text("print('v2')\n")
    digest, verdict = probe()
    assert verdict == "changed"  # the incident: code edited, plist untouched
    state.write_text(digest + "\n")
    assert probe()[1] == "unchanged"
    # review-2 2.1a: landing.py imports these at run time, so they count too.
    (lib / "fleet_targets.py").write_text("v2\n")
    digest, verdict = probe()
    assert verdict == "changed"
    state.write_text(digest + "\n")
    (lib / "unrelated.py").write_text("v2\n")
    assert probe()[1] == "unchanged"  # control/lib code landing never imports
    # review-2 2.1c: a tracked file deleted mid-edit fails with a clear message.
    (lib / "ansible_context.py").unlink()
    out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert out.returncode != 0
    assert "missing from the working tree" in out.stderr
    assert "control/lib/ansible_context.py" in out.stderr


def test_landing_code_hash_works_outside_a_git_checkout(tmp_path: Path) -> None:
    import subprocess

    task = _find(_load_tasks("serverapp_landing"), "Hash landing code the agents execute")
    script = "\n".join(
        line
        for line in task["ansible.builtin.shell"]["cmd"].splitlines()
        if line.strip() not in {"{% raw %}", "{% endraw %}"}
    )
    code = tmp_path / "control" / "landing"
    code.mkdir(parents=True)
    (code / "landing.py").write_text("print('v1')\n")
    for name in ("ansible_context.py", "fleet_targets.py", "site_discovery.py"):
        (tmp_path / "control" / "lib").mkdir(exist_ok=True)
        (tmp_path / "control" / "lib" / name).write_text("v1\n")
    env = {
        **os.environ,
        "REPO_ROOT": str(tmp_path),
        "CODE_PATHS": "control/landing control/lib/ansible_context.py control/lib/fleet_targets.py control/lib/site_discovery.py",
        "STATE_FILE": str(tmp_path / "state"),
        "GIT_CEILING_DIRECTORIES": str(tmp_path.parent),
    }
    out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True)
    digest, verdict = out.stdout.split()
    assert verdict == "changed" and len(digest) == 64
