#!/usr/bin/env python3
"""Shared cross-process lock guarding fleet-touching Mac-side scripts.

``deploy_fleet.py`` and ``termux_pkg_nightly.py`` both drive ansible-playbook
against the same devices over adb/ssh. Nothing previously stopped two
invocations — two manual deploys, or a manual deploy colliding with the
nightly package-upgrade launchd job — from running concurrently against the
same devices, risking corrupted partial writes or conflicting
package-manager state on-device (stayturgid issue #58).

This is a single non-blocking flock, not a queue: a second invocation fails
fast with a clear "already running" message rather than waiting or silently
racing. Scripts that already guard themselves against their own concurrent
runs (``adb_reconnect.py``'s per-device flock, the on-device
``stayturgid_repair.py`` lock) are unaffected — this only coordinates the
Mac-side entry points against each other.

Store: ``~/.config/stayturgid/locks/fleet-deploy.lock`` (override with
``STAYTURGID_FLEET_LOCK_PATH``).
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class FleetLockHeld(RuntimeError):
    """Another fleet-touching script already holds the lock."""

    def __init__(self, message: str, holder: dict[str, Any] | None = None):
        super().__init__(message)
        self.holder = holder or {}


def lock_path() -> Path:
    override = os.environ.get("STAYTURGID_FLEET_LOCK_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "stayturgid" / "locks" / "fleet-deploy.lock"


def _read_holder(fd) -> dict[str, Any]:
    try:
        fd.seek(0)
        data = json.loads(fd.read() or "{}")
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def format_holder(holder: dict[str, Any]) -> str:
    label = holder.get("label", "?")
    pid = holder.get("pid", "?")
    started = holder.get("started_at", "?")
    return "%s (pid %s, started %s)" % (label, pid, started)


@contextmanager
def fleet_lock(label: str) -> Iterator[None]:
    """Non-blocking exclusive lock; raises FleetLockHeld if already taken.

    *label* identifies the caller in the failure message shown to whoever
    hits the conflict, e.g. ``"deploy_fleet.py s24"``.
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(path, "a+")
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            holder = _read_holder(fd)
            raise FleetLockHeld(
                "another fleet-touching script is already running: %s" % format_holder(holder),
                holder=holder,
            ) from None
        fd.seek(0)
        fd.truncate()
        json.dump(
            {
                "label": label,
                "pid": os.getpid(),
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            fd,
        )
        fd.flush()
        try:
            yield
        finally:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
    finally:
        fd.close()
