"""The own-mode OpenObserve and OliveTin pins must actually gate the install.

Both roles used to consult their pinned version only when the binary was
absent, so bumping the pin upgraded nothing (OliveTin was pinned 3000.20.0 while
3000.17.1 ran). The shape mirrors tests/python/test_firerpa_version_lock.py:
probe in check mode, compare, fail open on anything unparseable, stamp last,
verify afterwards. The seven brew-managed serverapp_* roles are deliberately NOT
covered: install-if-absent is correct for them.
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLES = REPO / "ansible/roles"

# role -> (tag, pinned-version var, sample --version output, parsed version)
CASES = {
    "serverapp_openobserve": ("oo", "serverapp_openobserve_version", "openobserve v1.0.4", "1.0.4"),
    "serverapp_olivetin": (
        "ot",
        "serverapp_olivetin_version",
        'level="info" msg="OliveTin is just printing the startup message" '
        'commit="5c3d342" date="2026-07-17T16:29:45Z" version="3000.17.1"',
        "3000.17.1",
    ),
}


def _tasks(role: str) -> list[dict]:
    return yaml.safe_load((ROLES / role / "tasks/main.yml").read_text(encoding="utf-8"))


def _by_name(role: str, prefix: str) -> dict:
    matches = [t for t in _walk(_tasks(role)) if str(t.get("name", "")).startswith(prefix)]
    assert len(matches) == 1, (prefix, [m["name"] for m in matches])
    return matches[0]


def _walk(tasks: list[dict]):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            if key in task:
                yield from _walk(task[key])


def _env() -> jinja2.Environment:
    import re

    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.filters["regex_findall"] = lambda value, pattern: re.findall(pattern, value)
    return env


def _facts(role: str, stdout: str | None, *, bin_exists=True, webui_isdir=True) -> dict:
    tag, version_var, _sample, _parsed = CASES[role]
    task = _by_name(role, "Record whether")
    facts = task["ansible.builtin.set_fact"]
    ctx = {
        f"_{tag}_bin_stat": {"stat": {"exists": bin_exists}},
        f"_{tag}_webui_stat": {"stat": {"isdir": webui_isdir}},
        f"_{tag}_version_probe": {"stdout": stdout} if stdout is not None else {},
        version_var: {"serverapp_openobserve_version": "1.0.4", "serverapp_olivetin_version": "3000.20.0"}[version_var],
    }
    env = _env()
    out = {}
    for key, expr in facts.items():
        rendered = env.from_string(expr).render(**ctx).strip()
        out[key] = rendered
    return out


@pytest.mark.parametrize("role", CASES)
def test_pin_mismatch_triggers_install_and_match_does_not(role):
    tag, version_var, sample, parsed = CASES[role]
    pinned = {"serverapp_openobserve": "1.0.4", "serverapp_olivetin": "3000.20.0"}[role]
    facts = _facts(role, sample)
    assert facts[f"_{tag}_installed_version"] == parsed
    assert facts[f"_{tag}_install_required"] == str(parsed != pinned)
    # An up-to-date probe string must converge.
    matching = sample.replace(parsed, pinned)
    assert _facts(role, matching)[f"_{tag}_install_required"] == "False"
    # A downgrade is a mismatch too: the pin is the authority.
    assert _facts(role, sample.replace(parsed, "0.0.1"))[f"_{tag}_install_required"] == "True"


@pytest.mark.parametrize("role", CASES)
@pytest.mark.parametrize("garbage", ["", "no version here", "usage: openobserve [OPTIONS]\n"])
def test_unparseable_version_fails_open(role, garbage):
    """Never reinstall or block because a --version string changed format."""
    tag = CASES[role][0]
    facts = _facts(role, garbage)
    assert facts[f"_{tag}_installed_version"] == ""
    assert facts[f"_{tag}_install_required"] == "False"


@pytest.mark.parametrize("role", CASES)
def test_missing_probe_output_is_not_an_error(role):
    """A skipped/failed probe leaves a register with no stdout."""
    tag = CASES[role][0]
    assert _facts(role, None)[f"_{tag}_install_required"] == "False"


@pytest.mark.parametrize("role", CASES)
def test_absent_binary_still_installs(role):
    tag = CASES[role][0]
    assert _facts(role, "", bin_exists=False)[f"_{tag}_install_required"] == "True"


def test_olivetin_missing_webui_installs_even_when_binary_current():
    facts = _facts("serverapp_olivetin", 'version="3000.20.0"', webui_isdir=False)
    assert facts["_ot_install_required"] == "True"


@pytest.mark.parametrize("role", CASES)
def test_the_probe_runs_in_check_mode_so_dry_runs_are_honest(role):
    probe = _by_name(role, "Probe the installed")
    assert probe.get("check_mode") is False
    assert probe.get("changed_when") is False
    assert probe.get("failed_when") is False


@pytest.mark.parametrize("role", CASES)
def test_the_expensive_install_steps_are_all_gated(role):
    tag = CASES[role][0]
    gate = f"_{tag}_install_required"
    names = [
        "Detect machine architecture",
        "Set ",
        "Fail closed when no pinned checksum",
        "Create temporary directory",
        "Download, extract, and install",
    ]
    for prefix in names:
        task = (
            _by_name(role, prefix)
            if prefix != "Set "
            else next(t for t in _walk(_tasks(role)) if str(t.get("name", "")).endswith("download architecture fact"))
        )
        assert gate in str(task.get("when")), f"{task['name']} is not gated on {gate}"
    # No gate may still key on mere existence of the artifact.
    text = (ROLES / role / "tasks/main.yml").read_text(encoding="utf-8")
    for task in _walk(_tasks(role)):
        when = str(task.get("when", ""))
        if "Record whether" in task.get("name", "") or "Note an unparseable" in task.get("name", ""):
            continue
        if task.get("name", "").startswith(("Assert", "Check whether", "Probe the", "Note an")):
            continue
        assert f"_{tag}_bin_stat" not in when, task["name"]
    assert "(never upgrade)" not in text


@pytest.mark.parametrize("role", CASES)
def test_the_checksum_check_stays_fail_closed(role):
    task = _by_name(role, "Fail closed when no pinned checksum")
    assert "ansible.builtin.assert" in task
    get_url = next(t for t in _walk(_tasks(role)) if "ansible.builtin.get_url" in t)
    assert str(get_url["ansible.builtin.get_url"]["checksum"]).startswith("sha256:")


@pytest.mark.parametrize("role", CASES)
def test_check_mode_does_not_reach_tasks_that_need_a_download(role):
    """get_url does not download under --check, so extract/copy would fail on a
    missing source; the block must be skipped there and a debug note shown."""
    block = _by_name(role, "Download, extract, and install")
    assert "not ansible_check_mode" in str(block["when"])
    tmp = _by_name(role, "Create temporary directory")
    assert "not ansible_check_mode" in str(tmp["when"])
    uname = _by_name(role, "Detect machine architecture")
    assert uname.get("check_mode") is False
    note = _by_name(role, "Report pending")
    assert "ansible_check_mode" in str(note["when"])


@pytest.mark.parametrize("role", CASES)
def test_post_install_verification_guard_is_check_mode_and_skip_safe(role):
    """ansible.builtin.fail runs in check mode; and a skipped probe has no stdout."""
    tag = CASES[role][0]
    guard = _by_name(role, "Fail if")
    when = guard["when"]
    assert "not ansible_check_mode" in when
    assert f"_{tag}_install_required | bool" in when
    # Every read of the register tolerates a missing stdout.
    for cond in when:
        if f"_{tag}_version_verify" in cond:
            assert f"_{tag}_version_verify.stdout | default('')" in cond
    verify = next(t for t in _walk(_tasks(role)) if str(t.get("name", "")).endswith("version after install"))
    assert "not ansible_check_mode" in verify["when"]
    assert f"_{tag}_install_required | bool" in verify["when"]


@pytest.mark.parametrize("role", CASES)
def test_verification_runs_after_install_and_before_the_service_is_touched(role):
    names = [t["name"] for t in _tasks(role)]
    install = next(i for i, n in enumerate(names) if n.startswith("Download, extract, and install"))
    verify = next(i for i, n in enumerate(names) if n.startswith("Fail if"))
    plist = next(i for i, n in enumerate(names) if "launchd plist" in n and n.startswith("Render"))
    assert install < verify < plist


def test_olivetin_binary_is_installed_last_so_it_acts_as_the_stamp():
    """The probe trusts the binary's --version, so it must change only after the
    webui is in place, and the old webui must be removed, not merged over."""
    block = _by_name("serverapp_olivetin", "Download, extract, and install")["block"]
    names = [t["name"] for t in block]
    remove = names.index("Remove the previous OliveTin webui directory")
    webui = names.index("Install OliveTin webui directory")
    binary = names.index("Install OliveTin binary to install dir")
    assert remove < webui < binary
    assert block[remove]["ansible.builtin.file"]["state"] == "absent"
    # Nothing in the block is separately gated any more: both artifacts move together.
    for task in block[remove : binary + 1]:
        assert "when" not in task


@pytest.mark.parametrize("role", CASES)
def test_the_pins_are_unchanged(role):
    defaults = yaml.safe_load((ROLES / role / "defaults/main.yml").read_text(encoding="utf-8"))
    key = CASES[role][1]
    assert defaults[key] == {"serverapp_openobserve": "1.0.4", "serverapp_olivetin": "3000.20.0"}[role]
