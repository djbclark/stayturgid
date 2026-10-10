"""Run the real termux-pkg-upgrade.yml against fake local hosts (#310).

The nightly's unit tests fake ansible's output. This drives the actual
playbook, so the parts only ansible can check are covered: the delegated
result-file task, `now()`, the `is not unreachable` guard under
`ignore_unreachable`, and the termux_pkg module's new return values. Hosts:
one that upgrades, one whose `pkg update` fails (a dead mirror), one that
refuses SSH, and one with the upgrade disabled. No device, no network.
"""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import termux_pkg_nightly as nightly

REPO = Path(__file__).resolve().parents[2]
PLAYBOOK = REPO / "ansible" / "playbooks" / "fleet" / "termux-pkg-upgrade.yml"
ANSIBLE_PLAYBOOK = Path(sys.executable).with_name("ansible-playbook")

_FAKE_BASH = """#!/bin/bash
P="$(dirname "$0")/.."
case "$2" in
  *"pkg update"*)
    if [ -f "$P/fail-update" ]; then echo "E: Failed to fetch https://dead.mirror" >&2; exit 100; fi
    echo "Get:1 https://example stable InRelease"; exit 0 ;;
  *full-upgrade*)
    echo "1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
    echo "Setting up openssh (10.2p1-1) ..."; exit 0 ;;
esac
exit 0
"""


def _utf8_locale() -> str | None:
    """A UTF-8 locale this system accepts: ansible refuses to start without one,
    and agent shells and CI runners often export none (C.UTF-8 is absent on
    macOS, en_US.UTF-8 on some minimal Linux images)."""
    saved = locale.setlocale(locale.LC_CTYPE)
    try:
        for name in ("C.UTF-8", "en_US.UTF-8", "UTF-8"):
            try:
                locale.setlocale(locale.LC_CTYPE, name)
            except locale.Error:
                continue
            return name
    finally:
        locale.setlocale(locale.LC_CTYPE, saved)
    return None


def _prefix(root: Path, name: str, *, dead_mirror: bool = False) -> Path:
    prefix = root / name
    (prefix / "bin").mkdir(parents=True)
    (prefix / "etc" / "apt").mkdir(parents=True)
    bash = prefix / "bin" / "bash"
    bash.write_text(_FAKE_BASH, encoding="utf-8")
    bash.chmod(0o755)
    if dead_mirror:
        (prefix / "fail-update").touch()
    return prefix


@pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason="ansible-playbook not installed beside this python")
@pytest.mark.skipif(shutil.which("ssh") is None, reason="needs an ssh client for the unreachable host")
def test_playbook_writes_one_result_per_finished_host(tmp_path):
    local = {"ansible_connection": "local", "ansible_python_interpreter": sys.executable}
    hosts = {
        "fakeok": {**local, "termux_prefix": str(_prefix(tmp_path, "fakeok"))},
        "fakestale": {**local, "termux_prefix": str(_prefix(tmp_path, "fakestale", dead_mirror=True))},
        "fakedisabled": {
            **local,
            "termux_prefix": str(_prefix(tmp_path, "fakedisabled")),
            "stayturgid_termux_pkg_upgrade_enabled": False,
        },
        # Port 1 on loopback refuses at once: unreachable without a timeout.
        "fakeoff": {
            "ansible_connection": "ssh",
            "ansible_host": "127.0.0.1",
            "ansible_port": 1,
            "ansible_user": "nobody",
            "termux_prefix": "/nonexistent",
        },
    }
    inventory = tmp_path / "hosts.json"
    inventory.write_text(json.dumps({"stayturgid": {"hosts": hosts}}), encoding="utf-8")
    config = tmp_path / "ansible.cfg"
    config.write_text("", encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    utf8 = _utf8_locale()
    if utf8 is None:
        pytest.skip("no UTF-8 locale available for ansible")
    env = {
        **os.environ,
        "LC_ALL": utf8,
        "LANG": utf8,
        "ANSIBLE_CONFIG": str(config),
        "ANSIBLE_COLLECTIONS_PATH": str(REPO),
        "ANSIBLE_HOST_KEY_CHECKING": "False",
        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
        "ANSIBLE_REMOTE_TEMP": str(tmp_path / "ansible-remote"),
    }

    run = subprocess.run(
        [
            str(ANSIBLE_PLAYBOOK),
            "-i",
            str(inventory),
            str(PLAYBOOK),
            "-e",
            json.dumps({"stayturgid_termux_pkg_result_dir": str(results)}),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]

    written = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in results.glob("*.json")}
    assert set(written) == {"fakeok", "fakestale"}, "unreachable and disabled hosts must write no result"
    assert written["fakeok"]["upgraded_packages"] == ["openssh 10.2p1-1"]
    assert written["fakeok"]["index_update_failed"] is False
    assert written["fakestale"]["index_update_failed"] is True

    failures = nightly.parse_host_failures(run.stdout)
    outcomes = nightly.host_outcomes(
        nightly.parse_recap_hosts(run.stdout), nightly.read_host_results(results), failures
    )
    assert {h: o.status for h, o in outcomes.items()} == {
        "fakeok": "changed",
        "fakestale": "changed",
        "fakeoff": "unreachable",
    }
    assert all(o.duration_s is not None for h, o in outcomes.items() if h != "fakeoff")
    assert list(nightly.stale_index_hosts(outcomes)) == ["fakestale"]
