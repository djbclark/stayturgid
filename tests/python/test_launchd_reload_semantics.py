"""Assert launchd plist-change reload semantics (M1-F MF-3).

launchd caches the loaded plist definition; `kickstart -k` restarts a daemon
with the *old* definition, so a changed plist must go through
bootout-then-bootstrap, not kickstart. kickstart is only correct for
config-only changes. This test parses each serverapp role's tasks/main.yml
and asserts the task shapes rather than running ansible.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = ROOT / "ansible" / "roles"

# app -> (plist changed-register var, config changed-register var or None if
# the role has no kickstartable own-mode config template)
ROLES = {
    "vector": "_vector",
    "openobserve": "_oo",
    "caddy": "_caddy",
    "grafana": "_gf",
    "olivetin": "_ot",
}


def _load_tasks(app: str) -> list[dict]:
    path = ROLES_DIR / f"serverapp_{app}" / "tasks" / "main.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find(tasks: list[dict], substring: str) -> dict:
    matches = [t for t in tasks if substring in t.get("name", "")]
    assert len(matches) == 1, f"expected exactly one task matching {substring!r}, got {len(matches)}"
    return matches[0]


def _as_text(when) -> str:
    if isinstance(when, list):
        return " ".join(str(w) for w in when)
    return str(when)


def test_all_roles_boot_out_on_plist_change() -> None:
    for app, prefix in ROLES.items():
        tasks = _load_tasks(app)
        boot = _find(tasks, "when its launchd plist changed")
        when_text = _as_text(boot["when"])
        assert "loaded" in when_text
        assert f"{prefix}_plist.changed" in when_text


def test_all_roles_bootstrap_on_unloaded_or_plist_change_with_retries() -> None:
    for app, prefix in ROLES.items():
        tasks = _load_tasks(app)
        bootstrap = _find(tasks, "when unloaded or its plist changed")
        when_text = _as_text(bootstrap["when"])
        assert "unloaded" in when_text
        assert f"{prefix}_plist_reload_bootout.changed" in when_text
        assert bootstrap.get("retries") == 5, f"{app}: expected retries: 5, got {bootstrap.get('retries')!r}"
        assert "until" in bootstrap, f"{app}: bootstrap task missing until (must retry on failure)"


def test_kickstart_restricted_to_config_only_change() -> None:
    # openobserve has no own-mode config template that can change independently
    # of the plist, so it has no kickstart task at all — that's correct, not a gap.
    kickstartable = {app: prefix for app, prefix in ROLES.items() if app != "openobserve"}
    for app, prefix in kickstartable.items():
        tasks = _load_tasks(app)
        kickstart = _find(tasks, f"Kickstart site-namespace {app}")
        when_text = _as_text(kickstart["when"])
        assert f"{prefix}_plist.changed" in when_text
        assert "not" in when_text
