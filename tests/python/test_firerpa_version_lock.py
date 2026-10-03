"""Regression guards for the FIRERPA v10.9 pin.

Two jobs:

1. No stale v10.0 interpreter/artifact literal survives anywhere FIRERPA is
   actually driven from.  v10.9 moved the embedded runtime from Python 3.9 to
   3.12 and replaced the driver JAR with ``lamda/aab.zip``, and the paths are
   spread across the Ansible role, an on-device boot probe that runs *outside*
   Ansible, the shell-test doubles and the standalone example.  Nothing else in
   the suite would notice a missed one.
2. The pinned version and archive checksum cannot drift apart, in the spirit of
   ``test_bootstrap_apk_lock.py``.
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

FIRERPA_VERSION = "10.9"
SERVER_ARCHIVE_SHA256 = "88957c04f6cae2e2cc56aaece92cec4074ad72092bc05f1e26e4095de7dedeca"
ACTIVE_DRIVER_PATH = "lib/python3.12/site-packages/lamda/aab.zip"

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


def test_no_stale_v10_0_literals_where_firerpa_is_driven():
    offenders: list[str] = []
    scanned = 0
    for path in _scanned_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
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


def test_the_v10_9_driver_path_is_the_one_actually_used():
    """The patcher, the role and the lifecycle must agree on one path."""
    patcher = _module("firerpa_service_patch", PATCHER_PATH)
    lifecycle = _module("firerpa_lifecycle", LIFECYCLE_PATH)

    assert patcher.DRIVER_ARCHIVE_SUFFIX.endswith(ACTIVE_DRIVER_PATH.removeprefix("lib"))
    assert ACTIVE_DRIVER_PATH in INSTALL.read_text(encoding="utf-8")
    assert ACTIVE_DRIVER_PATH in LIFECYCLE_PATH.read_text(encoding="utf-8")
    assert lifecycle.DRIVER_ARCHIVE_FRAGMENT == "/site-packages/lamda/aab.zip"
    assert "server/bin/python3.12" in INSTALL.read_text(encoding="utf-8")


def _defaults() -> dict:
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


def test_version_and_checksum_are_locked_together():
    defaults = _defaults()
    assert defaults["firerpa_version"] == FIRERPA_VERSION
    assert defaults["firerpa_server_archive_sha256_arm64"] == SERVER_ARCHIVE_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", defaults["firerpa_server_archive_sha256_arm64"])


def test_archive_url_is_the_pinned_fork_mirror_for_this_version():
    """Upstream deletes releases (v10.0 and v10.2 are gone), so we fetch the mirror."""
    url = _defaults()["firerpa_server_archive_url_arm64"].strip()
    assert url.startswith("https://github.com/djbclark/lamda/releases/download/")
    assert "v{{ firerpa_version }}-binaries" in url
    assert "{{ firerpa_server_archive_arm64 }}" in url
    assert _defaults()["firerpa_server_archive_arm64"] == "lamda-server-arm64-v8a.tar.gz"


def test_the_role_verifies_the_archive_checksum_on_download():
    install = INSTALL.read_text(encoding="utf-8")
    assert 'checksum: "sha256:{{ firerpa_server_archive_sha256_arm64 }}"' in install


def test_driver_hashes_are_distinct_and_well_formed():
    lifecycle = _module("firerpa_lifecycle", LIFECYCLE_PATH)
    patcher = _module("firerpa_service_patch", PATCHER_PATH)
    digests = [
        lifecycle.SIGNED_DRIVER_SHA256,
        lifecycle.PATCHED_DRIVER_SHA256,
        patcher.ORIGINAL_DEX_SHA256,
        patcher.PATCHED_DEX_SHA256,
    ]
    for digest in digests:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest
    assert len(set(digests)) == len(digests), "a driver/DEX hash pin was copy-pasted"
