"""Regression guards for how the FIRERPA role installs the latest release.

Three jobs:

1. No stale v10.0 interpreter/artifact literal survives anywhere FIRERPA is
   actually driven from.  v10.9 moved the embedded runtime from Python 3.9 to
   3.12 and replaced the driver JAR with ``lamda/aab.zip``, and the paths are
   spread across the Ansible role, an on-device boot probe that runs *outside*
   Ansible, the shell-test doubles and the standalone example.  Nothing else in
   the suite would notice a missed one.
2. The version is resolved, not pinned, and the download is verified against
   the checksum upstream publishes for that release.
3. A converged device stays a no-op (#311) and the install steps stay gated.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa"
DEFAULTS = ROLE / "defaults/main.yml"
INSTALL = ROLE / "tasks/install.yml"
LIFECYCLE_PATH = ROLE / "files/firerpa_lifecycle.py"
PATCHER_PATH = ROLE / "files/firerpa_service_patch.py"

# Literals that were correct for v10.0 and are wrong for v10.9.  A file that
# still contains one is either dead or about to break on a live device.
STALE_LITERALS = ("python3.9", "service.jar")

# Everything that can actually drive a FIRERPA install.  docs/research/ is
# deliberately excluded: those are dated 2026-07-12 evaluations of v10.0 and are
# historical records, not instructions.
SCANNED_TREES = (
    ROLE.parent.parent,  # ansible_collections/stayturgid/firerpa
    REPO / "examples/firerpa-nonroot",
)
SCANNED_FILES = (
    REPO / "device/termux/py/start_adb.py",
    REPO / "tests/lib.sh",
    REPO / "tests/test-unit.sh",
    REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml",
    REPO / "control/bin/firerpa_health_monitor.py",
    REPO / "control/lib/firerpa_fleet.py",
)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scanned_text_files() -> list[Path]:
    found: list[Path] = []
    for tree in SCANNED_TREES:
        assert tree.is_dir(), tree
        found.extend(path for path in sorted(tree.rglob("*")) if path.is_file())
    for path in SCANNED_FILES:
        assert path.is_file(), path
        found.append(path)
    return found


# The one sanctioned appearance of a stale literal: the task that REMOVES the
# pre-v10.9 overrides from a device upgraded in place. Scoped to that single task
# so the guard stays absolute everywhere else.
MIGRATION_TASK = "Prepare FIRERPA driver override directory"


def _without_migration_task(text: str) -> str:
    if f"- name: {MIGRATION_TASK}" not in text:
        return text
    head, rest = text.split(f"- name: {MIGRATION_TASK}", 1)
    _dropped, tail = rest.split("\n- name: ", 1)
    return head + "\n- name: " + tail


def test_the_migration_cleanup_still_removes_the_pre_v10_9_overrides():
    """Guarded separately, so the sanctioned exception cannot quietly disappear."""
    install = INSTALL.read_text(encoding="utf-8")
    task = install.split(f"- name: {MIGRATION_TASK}", 1)[1].split("\n- name: ", 1)[0]
    assert "rm -f" in task
    assert "overrides/service.jar.signed" in task
    assert "overrides/service.jar.patched" in task


def test_no_stale_v10_0_literals_where_firerpa_is_driven():
    offenders: list[str] = []
    scanned = 0
    for path in _scanned_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        if path == INSTALL:
            text = _without_migration_task(text)
        scanned += 1
        for literal in STALE_LITERALS:
            if literal in text:
                lines = [
                    f"{path.relative_to(REPO)}:{number}"
                    for number, line in enumerate(text.splitlines(), 1)
                    if literal in line
                ]
                offenders.append(f"{literal!r} at {', '.join(lines)}")
    assert scanned > 10, f"guard scanned only {scanned} files; path list is probably wrong"
    assert not offenders, "stale v10.0 FIRERPA literals survive:\n" + "\n".join(offenders)


def test_the_driver_path_follows_the_embedded_python_minor_everywhere():
    """The patcher, the role and the lifecycle must agree on one path, and none
    may hard-code a single release's lib/python3.N."""
    patcher = _module("firerpa_service_patch", PATCHER_PATH)
    lifecycle = _module("firerpa_lifecycle", LIFECYCLE_PATH)
    driver_glob = "server/lib/python3.*/site-packages/lamda/aab.zip"

    for minor in ("3.12", "3.13"):
        assert patcher.DRIVER_ARCHIVE_PATTERN.search(f"server/lib/python{minor}/site-packages/lamda/aab.zip")
    assert driver_glob in INSTALL.read_text(encoding="utf-8")
    assert driver_glob.removeprefix("server/") in LIFECYCLE_PATH.read_text(encoding="utf-8")
    assert lifecycle.DRIVER_ARCHIVE_FRAGMENT == "/site-packages/lamda/aab.zip"
    for path in (INSTALL, PATCHER_PATH, LIFECYCLE_PATH):
        assert not re.search(r"python3\.[0-9]+/", path.read_text(encoding="utf-8")), path


def _defaults() -> dict:
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


def test_the_version_is_resolved_per_converge_not_pinned():
    defaults = _defaults()
    assert defaults["firerpa_version"] == "{{ hostvars['localhost']['firerpa_release_version'] }}"
    url = defaults["firerpa_server_archive_url_arm64"].strip()
    assert url.startswith("https://github.com/firerpa/lamda/releases/download/v{{ firerpa_version }}/")
    assert "firerpa_server_archive_sha256_arm64" not in defaults, "no checksum pin"


def test_the_download_is_verified_against_the_published_checksum():
    tasks = yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    by_name = {task["name"]: task for task in tasks}
    read = by_name["Read the published FIRERPA server archive checksum"]
    assert (
        "firerpa_server_archive_sha256sum_url_arm64"
        in read["ansible.builtin.set_fact"]["_firerpa_server_archive_sha256"]
    )
    assert by_name["Download FIRERPA server archive on Mac"]["ansible.builtin.get_url"]["checksum"] == (
        "sha256:{{ _firerpa_server_archive_sha256 }}"
    )
    assert (
        _defaults()["firerpa_server_archive_sha256sum_url_arm64"] == "{{ firerpa_server_archive_url_arm64 }}.sha256sum"
    )


def test_the_patcher_is_told_which_release_it_is_patching():
    """Without --version the patcher could not refuse a release it has no entry for."""
    tasks = yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    patch = next(t for t in tasks if t["name"] == "Patch FIRERPA driver for accessibility service coexistence")
    argv = patch["ansible.builtin.command"]["argv"]
    assert argv[argv.index("--version") + 1] == "{{ firerpa_version }}"
    names = [t["name"] for t in tasks]
    assert names.index("Patch FIRERPA driver for accessibility service coexistence") < names.index(
        "Push server archive to device via adb"
    ), "the patch must refuse an unvetted release before the device is touched"


def test_the_lifecycle_and_patcher_vet_the_same_driver_pairs():
    """The lifecycle is pushed alone and cannot import the patcher, so it keeps a copy."""
    lifecycle = _module("firerpa_lifecycle", LIFECYCLE_PATH)
    patcher = _module("firerpa_service_patch", PATCHER_PATH)
    assert lifecycle.SUPPORTED_DRIVERS == {
        version: (spec.signed_archive_sha256, spec.patched_archive_sha256)
        for version, spec in patcher.SUPPORTED_DRIVERS.items()
    }


def test_certificate_path_is_absolute_before_it_reaches_adb():
    """`adb push` cannot stat a literal "~/..." path, and the tracked secretspec
    default for FIRERPA_CERTIFICATE is exactly that, so the role must expanduser it."""
    defaults = DEFAULTS.read_text(encoding="utf-8")
    assert "expanduser" in defaults
    expression = defaults.split("firerpa_certificate_path:", 1)[1].split("firerpa_certificate_device_path:", 1)[0]
    assert "| expanduser" in expression, "firerpa_certificate_path must be expanduser'd"


def test_post_extract_guard_does_not_fire_in_check_mode():
    """#311 put this role in the plain-deploy path, so `just deploy-check` runs it.

    Every adb step is a command/shell task, which --check skips, so the verify
    task registers no stdout and `'OK' not in ''` is true. ansible.builtin.fail
    *does* run in check mode, so without the ansible_check_mode guard a dry run
    fails on every host that opts into FIRERPA.
    """
    install = INSTALL.read_text(encoding="utf-8")
    guard = install.split("- name: Fail if FIRERPA binary missing after extract", 1)[1]
    guard = guard.split("\n- name:", 1)[0]
    assert "not ansible_check_mode" in guard


# --- #311 follow-up: a converged device must be a no-op -----------------------

GATE = "_firerpa_install_required"


def test_install_is_gated_on_a_version_and_checksum_stamp():
    """#311 put this role in the plain-deploy path, so an unconditional ~204 MiB
    download + push ran on every opted-in host on every deploy."""
    defaults = _defaults()
    stamp = defaults["firerpa_version_stamp"]
    # Version alone would miss a re-published release with new bytes.
    assert "{{ firerpa_version }}" in stamp
    assert "{{ _firerpa_server_archive_sha256 }}" in stamp


def test_the_expensive_install_steps_are_all_gated():
    import yaml as _yaml

    tasks = _yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    by_name = {task["name"]: task for task in tasks}
    expensive = [
        "Download FIRERPA server archive on Mac",
        "Patch FIRERPA driver for accessibility service coexistence",
        "Push server archive to device via adb",
        "Stop existing FIRERPA process tree before replacing files",
        "Extract server via adb shell",
        "Preserve signed FIRERPA driver for integrity validation",
        "Install accessibility-compatible FIRERPA driver override",
    ]
    for name in expensive:
        assert name in by_name, name
        when = by_name[name].get("when")
        assert when is not None, f"{name} is not gated"
        assert GATE in str(when), f"{name} is not gated on {GATE}"


def test_the_probe_runs_in_check_mode_so_dry_runs_are_honest():
    import yaml as _yaml

    tasks = _yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    probe = next(t for t in tasks if t["name"].startswith("Detect whether the device already"))
    assert probe.get("check_mode") is False
    assert probe.get("changed_when") is False


def test_the_stamp_is_written_only_after_a_verified_install():
    """A partial install must leave the old stamp, so the next run redoes the work."""
    install = INSTALL.read_text(encoding="utf-8")
    stamp_at = install.index("Record the installed FIRERPA build on the device")
    verify_at = install.index("Verify FIRERPA server binary exists after extract")
    fail_at = install.index("Fail if FIRERPA binary missing after extract")
    assert verify_at < fail_at < stamp_at, "the stamp must be written last"


def test_the_lifecycle_wrapper_is_pushed_even_on_a_converged_device():
    """The wrapper is a repo file, so a converged device must still get its changes."""
    import yaml as _yaml

    tasks = _yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    by_name = {task["name"]: task for task in tasks}
    wrapper = by_name["Install Python FIRERPA lifecycle wrapper"]
    assert "when" not in wrapper, "the lifecycle wrapper push must not be gated"
