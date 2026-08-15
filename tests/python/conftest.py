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


@pytest.fixture(autouse=True)
def _secretspec_boundary_present(monkeypatch) -> Iterator[None]:
    """Pin secretspec_exec to the privilege-separated boundary path.

    Call sites build their argv via control/lib/secretspec_exec.py, which picks
    the brokered form only when the `sudo-secretspec` companion is on PATH.
    That is true on the control node and false on a CI runner, so tests
    asserting an exact argv would otherwise pass locally and fail in CI --
    precisely the local/CI divergence this module was added to fix.

    Tests that specifically exercise the fallback re-patch `boundary_available`
    themselves; the later monkeypatch wins over this autouse one.

    Both spellings must be patched. conftest puts `control/lib` *and* the repo
    root on sys.path, so `import secretspec_exec` and
    `from control.lib.secretspec_exec import ...` produce two independent module
    objects, each with its own `boundary_available` and its own lru_cache — and
    the call sites are split across both conventions (matching how
    ansible_context is already imported repo-wide). Patching only one leaves the
    other live, which passes on a control node (where the real function returns
    True anyway) and fails in CI.
    """
    import importlib

    reals = []
    for name in ("secretspec_exec", "control.lib.secretspec_exec"):
        module = importlib.import_module(name)
        # Hold the real (lru_cached) function: once monkeypatch replaces the
        # attribute it no longer carries .cache_clear(), and this fixture's
        # teardown runs before monkeypatch's undo.
        real = module.boundary_available
        real.cache_clear()
        monkeypatch.setattr(module, "boundary_available", lambda: True)
        reals.append(real)
    yield
    for real in reals:
        real.cache_clear()
