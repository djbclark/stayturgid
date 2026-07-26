"""Shared pytest paths for the script-twin tests (tests/python/).

The Ansible *module* (termux_pkg) is tested inside the collection via
`ansible-test units`; these plain-pytest tests cover the Termux Python
script twins under device/termux/py/ and control/lib helpers.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
sys.path.insert(0, os.path.join(REPO, "control", "bin"))
sys.path.insert(0, os.path.join(REPO, "device", "termux", "py"))

# device/termux/py/start_adb.py mutates os.environ at import time (Termux
# PREFIX/TMPDIR/HOME). Pytest collection imports that module, which would
# leave host `just` wrappers writing under a non-existent Termux path.
# Snapshot the host values before collection and restore after every test.
_HOST_ENV_KEYS = ("TMPDIR", "TEMP", "TMP", "HOME", "PREFIX", "LD_LIBRARY_PATH", "PATH")
_HOST_ENV_SNAPSHOT = {key: os.environ.get(key) for key in _HOST_ENV_KEYS}


def _restore_host_env() -> None:
    for key, value in _HOST_ENV_SNAPSHOT.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def pytest_collection_finish(session: pytest.Session) -> None:
    """Undo Termux boot-supervisor env mutations performed during collection."""
    _restore_host_env()


@pytest.fixture(autouse=True)
def _host_env_guard() -> Iterator[None]:
    """Keep host TMPDIR/HOME stable even if a test imports start_adb mid-run."""
    _restore_host_env()
    yield
    _restore_host_env()


@pytest.fixture(autouse=True)
def _fleet_lock_path(tmp_path, monkeypatch) -> None:
    """Point the shared fleet-deploy flock at a per-test tmp path.

    Without this, every test touching deploy_fleet.py/termux_pkg_nightly.py
    would flock the developer's real ~/.config/stayturgid/locks/fleet-deploy.lock,
    risking a spurious FleetLockHeld if a real deploy happens to be running,
    and leaving test runs non-hermetic/non-parallel-safe.
    """
    monkeypatch.setenv("STAYTURGID_FLEET_LOCK_PATH", str(tmp_path / "fleet-deploy.lock"))
