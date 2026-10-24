"""The own-mode OpenObserve, OliveTin and blackbox_exporter roles track the latest
upstream release, and that version must actually gate the install.

Site policy (djbclark 2026-10-24): installed software tracks the latest release,
no version or checksum is pinned. Each role resolves the latest release at
converge time (the shared github_latest_release role), asks the installed binary
what it is, and reinstalls + restarts when the two differ. The shape mirrors
tests/python/test_firerpa_version_lock.py: probe in check mode, compare, fail
open on anything unparseable, stamp last, verify afterwards. The latest-version
lookup itself is mocked here (a plain fact); tests/python/test_github_latest_release_role.py
runs that role against a local fake API.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLES = REPO / "ansible/roles"

# role -> (tag, GitHub repo, sample --version output, parsed version)
CASES = {
    "serverapp_openobserve": ("oo", "openobserve/openobserve", "openobserve v1.0.4", "1.0.4"),
    "serverapp_olivetin": (
        "ot",
        "OliveTin/OliveTin",
        'level="info" msg="OliveTin is just printing the startup message" '
        'commit="5c3d342" date="2026-07-17T16:29:45Z" version="3000.17.1"',
        "3000.17.1",
    ),
    "serverapp_blackbox_exporter": (
        "bbe",
        "prometheus/blackbox_exporter",
        "blackbox_exporter, version 0.28.0 (branch: HEAD, revision: 5a059bee8d8ffa4e75947c5055fb0abeefc582e6)\n"
        "  build user:       root@967d444a1ba3\n",
        "0.28.0",
    ),
}
# What the mocked latest-release lookup answers.
LATEST = {"serverapp_openobserve": "1.1.2", "serverapp_olivetin": "3000.21.0", "serverapp_blackbox_exporter": "0.29.1"}


def _tasks(role: str) -> list[dict]:
    return yaml.safe_load((ROLES / role / "tasks/main.yml").read_text(encoding="utf-8"))


def _walk(tasks: list[dict]):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            if key in task:
                yield from _walk(task[key])


def _by_name(role: str, prefix: str) -> dict:
    matches = [t for t in _walk(_tasks(role)) if str(t.get("name", "")).startswith(prefix)]
    assert len(matches) == 1, (prefix, [m["name"] for m in matches])
    return matches[0]


def _env() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.filters["regex_findall"] = lambda value, pattern: re.findall(pattern, value)
    return env


def _facts(role: str, stdout: str | None, *, bin_exists=True, webui_isdir=True) -> dict:
    tag = CASES[role][0]
    task = _by_name(role, "Record whether")
    ctx = {
        f"_{tag}_bin_stat": {"stat": {"exists": bin_exists}},
        f"_{tag}_webui_stat": {"stat": {"isdir": webui_isdir}},
        f"_{tag}_version_probe": {"stdout": stdout} if stdout is not None else {},
        f"_{tag}_latest_version": LATEST[role],
        # openobserve's stamp: a converged one, so only the version gate is exercised.
        "_oo_stamp_recorded": LATEST[role],
        "_oo_stamp_expected": LATEST[role],
    }
    env = _env()
    return {key: env.from_string(expr).render(**ctx).strip() for key, expr in task["ansible.builtin.set_fact"].items()}


@pytest.mark.parametrize("role", CASES)
def test_a_version_other_than_latest_triggers_install_and_latest_does_not(role):
    tag, _repo, sample, parsed = CASES[role]
    facts = _facts(role, sample)
    assert facts[f"_{tag}_installed_version"] == parsed
    assert facts[f"_{tag}_install_required"] == "True"
    # An up-to-date probe string must converge.
    assert _facts(role, sample.replace(parsed, LATEST[role]))[f"_{tag}_install_required"] == "False"
    # Newer than latest (a release pulled upstream) is a mismatch too: latest is the authority.
    assert _facts(role, sample.replace(parsed, "9999.0.0"))[f"_{tag}_install_required"] == "True"


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
    facts = _facts("serverapp_olivetin", f'version="{LATEST["serverapp_olivetin"]}"', webui_isdir=False)
    assert facts["_ot_install_required"] == "True"


@pytest.mark.parametrize("role", CASES)
def test_the_latest_release_is_resolved_before_the_install_decision(role):
    tag, repo, _sample, _parsed = CASES[role]
    resolve = next(
        t for t in _tasks(role) if t.get("ansible.builtin.include_role", {}).get("name") == "github_latest_release"
    )
    assert resolve["vars"] == {"github_latest_release_repo": repo}
    remember = _by_name(role, "Remember the latest")
    assert remember["ansible.builtin.set_fact"] == {f"_{tag}_latest_version": "{{ github_latest_release_version }}"}
    names = [t.get("name") for t in _tasks(role)]
    assert names.index(resolve["name"]) < names.index(remember["name"])
    assert names.index(remember["name"]) < next(i for i, n in enumerate(names) if n.startswith("Record whether"))


@pytest.mark.parametrize("role", CASES)
def test_nothing_is_pinned(role):
    """No version var, no checksum table, no fail-closed checksum assert, no get_url checksum."""
    defaults = yaml.safe_load((ROLES / role / "defaults/main.yml").read_text(encoding="utf-8"))
    assert not [key for key in defaults if key.endswith(("_version", "_sha256"))]
    text = (ROLES / role / "tasks/main.yml").read_text(encoding="utf-8")
    assert "Fail closed when no pinned checksum" not in text
    assert "_archive_sha256" not in text
    get_url = next(t for t in _walk(_tasks(role)) if "ansible.builtin.get_url" in t)
    assert "checksum" not in get_url["ansible.builtin.get_url"]


DOWNLOAD_URLS = {
    "serverapp_openobserve": (
        "https://downloads.openobserve.ai/releases/o2-enterprise/v1.1.2/openobserve-ee-v1.1.2-darwin-arm64.tar.gz"
    ),
    "serverapp_olivetin": "https://github.com/OliveTin/OliveTin/releases/download/3000.21.0/OliveTin-darwin-arm64.tar.gz",
    "serverapp_blackbox_exporter": (
        "https://github.com/prometheus/blackbox_exporter/releases/download/"
        "v0.29.1/blackbox_exporter-0.29.1.darwin-arm64.tar.gz"
    ),
}


@pytest.mark.parametrize("role", CASES)
def test_the_download_is_the_latest_release(role):
    tag = CASES[role][0]
    get_url = next(t for t in _walk(_tasks(role)) if "ansible.builtin.get_url" in t)
    env = _env()
    ctx = {f"_{tag}_latest_version": LATEST[role], f"_{tag}_arch": "darwin-arm64"}
    ctx.update({key: env.from_string(value).render(**ctx) for key, value in get_url.get("vars", {}).items()})
    assert env.from_string(get_url["ansible.builtin.get_url"]["url"]).render(**ctx) == DOWNLOAD_URLS[role]


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
    for prefix in ["Detect machine architecture", "Create temporary directory", "Download, extract, and install"]:
        task = _by_name(role, prefix)
        assert gate in str(task.get("when")), f"{task['name']} is not gated on {gate}"
    arch_fact = next(t for t in _walk(_tasks(role)) if str(t.get("name", "")).endswith("download architecture fact"))
    assert gate in str(arch_fact.get("when"))
    # No gate may still key on mere existence of the artifact.
    text = (ROLES / role / "tasks/main.yml").read_text(encoding="utf-8")
    for task in _walk(_tasks(role)):
        name = task.get("name", "")
        if name.startswith(("Record whether", "Assert", "Check whether", "Probe the", "Note an")):
            continue
        assert f"_{tag}_bin_stat" not in str(task.get("when", "")), name
    assert "(never upgrade)" not in text


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
    guard = next(
        t for t in _walk(_tasks(role)) if str(t.get("name", "")).endswith("is not at the latest version after install")
    )
    when = guard["when"]
    assert "not ansible_check_mode" in when
    assert f"_{tag}_install_required | bool" in when
    assert any(f"!= _{tag}_latest_version" in cond for cond in when)
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


# ---------------------------------------------------------------------------
# Installing a binary is not the same as running it. launchd keeps the old
# executable held open, so without a restart an upgrade lands on disk while
# the service keeps serving the previous build -- and the post-install
# `--version` probe reads the on-disk binary, so the assert passes green on a
# stale process. The brew-managed serverapps get this from serverapp_launchd;
# these three bootstrap launchd themselves, so they must do it.
# ---------------------------------------------------------------------------

STALE_DETECT = {
    "serverapp_openobserve": "Detect whether the running openobserve is on a stale binary",
    "serverapp_olivetin": "Detect whether the running OliveTin is on a stale binary",
    "serverapp_blackbox_exporter": "Detect whether the running blackbox_exporter is on a stale binary",
}
KICKSTART = {
    "serverapp_openobserve": "Restart openobserve when it is running a stale binary",
    "serverapp_olivetin": "Kickstart site-namespace olivetin after a config-only or binary change",
    "serverapp_blackbox_exporter": "Kickstart site-namespace blackbox_exporter after a config-only or binary change",
}
STALE_FAIL = {
    "serverapp_openobserve": "Fail if openobserve is still on a stale binary after the restart",
    "serverapp_olivetin": "Fail if OliveTin is still on a stale binary after the restart",
    "serverapp_blackbox_exporter": "Fail if blackbox_exporter is still on a stale binary after the restart",
}


@pytest.mark.parametrize("role", CASES)
def test_a_stale_running_binary_is_detected(role):
    """The gate is pointless if the new binary never gets run."""
    task = _by_name(role, STALE_DETECT[role])
    cmd = task["ansible.builtin.command"]["cmd"]
    assert "serverapp_binary_state.sh" in cmd, "must reuse the shared state script"
    # It compares the held-open executable, so it needs uid, label and binary.
    for var in ("_uid", "_label", "_bin_path"):
        assert var in cmd, f"{var} missing from the probe invocation"
    assert task.get("changed_when") is False
    # Without this a dry run cannot report a pending restart.
    assert task.get("check_mode") is False


@pytest.mark.parametrize("role", CASES)
def test_the_restart_fires_on_a_stale_binary(role):
    task = _by_name(role, KICKSTART[role])
    assert "kickstart -k" in task["ansible.builtin.command"]["cmd"]
    when = " ".join(str(c) for c in task["when"])
    assert "stale" in when, "the restart must key on the stale-binary probe"


@pytest.mark.parametrize("role", CASES)
def test_the_stale_restart_is_verified_and_check_mode_safe(role):
    """`ansible.builtin.fail` runs in check mode, so it must be gated."""
    task = _by_name(role, STALE_FAIL[role])
    when = " ".join(str(c) for c in task["when"])
    assert "not ansible_check_mode" in when
    # Only assert after we actually restarted something.
    assert "_kickstart" in when
    # Reading a skipped register must not explode.
    assert "default(" in when


@pytest.mark.parametrize("role", CASES)
def test_the_restart_happens_after_the_binary_is_installed(role):
    """Restarting before the copy would just re-run the old binary."""
    names = [str(t.get("name", "")) for t in _walk(_tasks(role))]
    detect = names.index(STALE_DETECT[role])
    installs = [i for i, n in enumerate(names) if n.startswith("Install ")]
    assert installs, "expected at least one install task"
    assert detect > max(installs), "stale detection must follow every install"


# ---------------------------------------------------------------------------
# The openobserve stamp (operator decision 2026-10-03: harden rather than accept
# the limit). A version gate whose only evidence is "the binary copy happened"
# trusts a half-finished install. The stamp is written strictly AFTER the
# post-install verify passes, so a partial install leaves the old stamp (or
# none) and the next run redoes everything.
# ---------------------------------------------------------------------------

OO = "serverapp_openobserve"


def _oo_install_required(stamp_recorded, stamp_expected, *, bin_exists=True, probe="openobserve v1.1.2"):
    task = _by_name(OO, "Record whether")
    expr = task["ansible.builtin.set_fact"]["_oo_install_required"]
    ctx = {
        "_oo_bin_stat": {"stat": {"exists": bin_exists}},
        "_oo_version_probe": {"stdout": probe},
        "_oo_stamp_recorded": stamp_recorded,
        "_oo_stamp_expected": stamp_expected,
        "_oo_latest_version": "1.1.2",
    }
    return _env().from_string(expr).render(**ctx).strip()


def test_a_matching_stamp_converges():
    assert _oo_install_required("1.1.2", "1.1.2") == "False"


def test_a_missing_stamp_installs():
    """Fail open in the safe direction: no evidence means do the work."""
    assert _oo_install_required("", "1.1.2") == "True"


def test_an_old_pinned_stamp_reinstalls_once():
    """Stamps written while a checksum was pinned read "<version> <sha256>"."""
    assert (
        _oo_install_required("1.1.2 7acc59cc63c8fd6afd5765bb34471e8d5eec9d6ccf8485c941aa13df6500fff6", "1.1.2")
        == "True"
    )


def test_the_stamp_is_the_latest_version():
    task = _by_name(OO, "Compute the expected and recorded openobserve stamps")
    assert task["ansible.builtin.set_fact"]["_oo_stamp_expected"] == "{{ _oo_latest_version }}"


def test_the_stamp_is_written_strictly_after_the_verify():
    """The ordering IS the property. A 'stamp exists' test passes an ordering bug."""
    names = [str(t.get("name", "")) for t in _walk(_tasks(OO))]
    verify = names.index("Fail if openobserve is not at the latest version after install")
    write = names.index("Record the installed openobserve build")
    assert write > verify, "stamp must be recorded only after the version verify passes"
    # And after every install step, for the same reason.
    installs = [i for i, n in enumerate(names) if n.startswith("Download, extract, and install")]
    assert installs and write > max(installs)


def test_the_stamp_write_is_check_mode_and_decision_gated():
    task = _by_name(OO, "Record the installed openobserve build")
    when = " ".join(str(c) for c in task["when"])
    assert "not ansible_check_mode" in when, "a dry run must not record a stamp it did not earn"
    assert "_oo_install_required" in when


def test_openobserve_health_url_tracks_the_base_uri():
    """ZO_BASE_URI remaps every HTTP route including healthz, so a hardcoded
    health URL is a gate that can never pass against a prefixed service."""
    defaults = yaml.safe_load((ROLES / OO / "defaults/main.yml").read_text(encoding="utf-8"))
    expr = defaults["serverapp_openobserve_health_url"]

    assert "serverapp_openobserve_base_uri" in expr, "health URL ignores base_uri"
    # And it must not re-hardcode what the address/port vars already say.
    assert "127.0.0.1" not in expr, "address is duplicated instead of referenced"
    assert "5080" not in expr, "port is duplicated instead of referenced"

    env = _env()
    for base_uri, expected in (("", "http://127.0.0.1:5080/healthz"), ("/oo", "http://127.0.0.1:5080/oo/healthz")):
        rendered = env.from_string(expr).render(
            serverapp_openobserve_http_address="127.0.0.1",
            serverapp_openobserve_http_port="5080",
            serverapp_openobserve_base_uri=base_uri,
        )
        assert " ".join(rendered.split()) == expected, f"base_uri={base_uri!r} -> {rendered!r}"
