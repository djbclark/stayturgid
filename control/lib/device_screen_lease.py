#!/usr/bin/env python3
"""Cross-project device screen-control lease (DSCL v1).

Shared Mac-side registry so multiple agents/projects (stayturgid and others)
do not fight over the same phone glass.

Canonical store (vendor-neutral — not stayturgid-specific)::

  ~/.local/state/device-screen-control/leases/<device_key>.json

Override root with env ``DEVICE_SCREEN_CONTROL_DIR``.

See docs/modules/screen-control-lease.md for the full protocol and the
interop prompt for other projects.
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "device-screen-control-lease/v1"
DEFAULT_TTL_SEC = 1800
DEFAULT_PROJECT = "stayturgid"

# Heartbeat / soft-stale: holders should refresh at least this often while
# actively controlling. Readers treat expires_at as hard deadline.
DEFAULT_HEARTBEAT_SEC = 60


class LeaseConflict(RuntimeError):
    """Another project/session holds an active lease for this device."""

    def __init__(self, message: str, lease: dict[str, Any] | None = None):
        super().__init__(message)
        self.lease = lease or {}


def lease_root() -> Path:
    override = os.environ.get("DEVICE_SCREEN_CONTROL_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "device-screen-control"
    return Path.home() / ".local" / "state" / "device-screen-control"


def leases_dir() -> Path:
    return lease_root() / "leases"


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    t = ts if ts is not None else _now()
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        raw = str(s).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).timestamp()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def device_key(device: str) -> str:
    """Filesystem-safe primary key for a device alias/serial."""
    raw = (device or "unknown").strip().lower()
    out = []
    for ch in raw:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        else:
            out.append("_")
    key = "".join(out).strip("._") or "unknown"
    return key[:120]


def lease_path(device: str) -> Path:
    return leases_dir() / ("%s.json" % device_key(device))


def project_id() -> str:
    return (
        os.environ.get("DEVICE_SCREEN_CONTROL_PROJECT")
        or os.environ.get("STAYTURGID_SCREEN_PROJECT")
        or DEFAULT_PROJECT
    ).strip() or DEFAULT_PROJECT


def agent_id(default: str = "Auto") -> str:
    return (
        os.environ.get("DEVICE_SCREEN_CONTROL_AGENT")
        or os.environ.get("STAYTURGID_AGENT")
        or default
    ).strip() or default


def force_acquire() -> bool:
    return os.environ.get("DEVICE_SCREEN_CONTROL_FORCE", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.environ.get("STAYTURGID_SCREEN_LEASE_FORCE", "").lower() in (
        "1",
        "true",
        "yes",
    )


def wait_sec() -> float:
    raw = os.environ.get("DEVICE_SCREEN_CONTROL_WAIT_SEC") or os.environ.get(
        "STAYTURGID_SCREEN_LEASE_WAIT_SEC", "0"
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def _lease_lock() -> Iterator[None]:
    """Exclusive lock around lease check+write (cross-process TOCTOU guard)."""
    root = lease_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".acquire.lock"
    fd = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fd.close()


def is_active(lease: dict[str, Any] | None, *, now: float | None = None) -> bool:
    if not lease:
        return False
    now = _now() if now is None else now
    exp = lease.get("expires_at")
    ts = _parse_iso(exp) if isinstance(exp, str) else None
    if ts is None:
        # fallback numeric expires (unix)
        try:
            ts = float(lease.get("expires", 0) or 0)
        except (TypeError, ValueError):
            return False
    return ts > now


def holder_project(lease: dict[str, Any]) -> str:
    h = lease.get("holder") if isinstance(lease.get("holder"), dict) else {}
    return str(h.get("project") or lease.get("project") or "").strip()


def holder_session(lease: dict[str, Any]) -> str:
    h = lease.get("holder") if isinstance(lease.get("holder"), dict) else {}
    return str(h.get("session_id") or lease.get("session_id") or "").strip()


def lease_device_ids(lease: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    d = lease.get("device")
    if d:
        ids.add(device_key(str(d)))
        ids.add(str(d).strip().lower())
    raw = lease.get("device_ids") or []
    if isinstance(raw, list):
        for item in raw:
            if item:
                ids.add(device_key(str(item)))
                ids.add(str(item).strip().lower())
    return ids


def load_lease(device: str) -> dict[str, Any] | None:
    """Load lease file for *device* key if present (may be expired)."""
    return _read_json(lease_path(device))


def list_leases(*, active_only: bool = True) -> list[dict[str, Any]]:
    root = leases_dir()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        data = _read_json(path)
        if not data:
            continue
        if active_only and not is_active(data):
            continue
        data = dict(data)
        data["_path"] = str(path)
        out.append(data)
    return out


def find_active_lease(*device_keys: str) -> dict[str, Any] | None:
    """Find any active lease matching any of the given aliases/serials."""
    keys = {device_key(k) for k in device_keys if k}
    keys |= {str(k).strip().lower() for k in device_keys if k}
    if not keys:
        return None
    for lease in list_leases(active_only=True):
        if lease_device_ids(lease) & keys:
            return lease
    return None


def format_holder(lease: dict[str, Any]) -> str:
    h = lease.get("holder") if isinstance(lease.get("holder"), dict) else {}
    project = h.get("project") or lease.get("project") or "?"
    agent = h.get("agent") or lease.get("agent") or "?"
    purpose = lease.get("purpose") or ""
    exp = lease.get("expires_at") or ""
    bits = ["project=%s" % project, "agent=%s" % agent]
    if purpose:
        bits.append("purpose=%s" % purpose)
    if exp:
        bits.append("expires=%s" % exp)
    return " ".join(bits)


def build_lease(
    device: str,
    *,
    device_ids: list[str] | None = None,
    project: str | None = None,
    agent: str | None = None,
    purpose: str = "",
    session_id: str | None = None,
    ttl_sec: int = DEFAULT_TTL_SEC,
    pid: int | None = None,
) -> dict[str, Any]:
    now = _now()
    ttl = int(ttl_sec) if ttl_sec > 0 else DEFAULT_TTL_SEC
    ids = [device]
    if device_ids:
        ids.extend(device_ids)
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for i in ids:
        s = str(i).strip()
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        uniq.append(s)
    return {
        "schema": SCHEMA,
        "device": device,
        "device_ids": uniq,
        "holder": {
            "project": project or project_id(),
            "agent": agent or agent_id(),
            "session_id": session_id or str(uuid.uuid4()),
            "pid": int(pid if pid is not None else os.getpid()),
            "hostname": socket.gethostname(),
        },
        "purpose": purpose or "",
        "started_at": _iso(now),
        "heartbeat_at": _iso(now),
        "expires_at": _iso(now + ttl),
        "ttl_sec": ttl,
    }


def ours(lease: dict[str, Any], *, session_id: str | None = None) -> bool:
    if holder_project(lease) != project_id():
        return False
    if session_id and holder_session(lease) and holder_session(lease) != session_id:
        return False
    return True


def acquire(
    device: str,
    *,
    device_ids: list[str] | None = None,
    purpose: str = "",
    agent: str | None = None,
    project: str | None = None,
    ttl_sec: int = DEFAULT_TTL_SEC,
    session_id: str | None = None,
    wait: float | None = None,
    force: bool | None = None,
) -> dict[str, Any]:
    """Acquire or renew a lease. Raises LeaseConflict if another holder is active.

    Same project + same process may renew. Same project different session:
    takes over after warning via return (still succeeds) unless force is false
    and wait expires — actually same-project takeover is allowed with replace.
    Cross-project: block unless force or wait until free.
    """
    force = force_acquire() if force is None else force
    wait = wait_sec() if wait is None else max(0.0, float(wait))
    deadline = _now() + wait
    keys = [device] + list(device_ids or [])
    sid = session_id or str(uuid.uuid4())
    proj = project or project_id()

    while True:
        with _lease_lock():
            existing = find_active_lease(*keys)
            can_write = existing is None
            if not can_write and ours(existing, session_id=None) and (
                holder_session(existing) == sid
                or existing.get("holder", {}).get("pid") == os.getpid()
            ):
                can_write = True
            if not can_write and force:
                can_write = True
            if can_write:
                lease = build_lease(
                    device,
                    device_ids=device_ids,
                    project=proj,
                    agent=agent,
                    purpose=purpose,
                    session_id=sid,
                    ttl_sec=ttl_sec,
                )
                primary = lease_path(device)
                _write_json_atomic(primary, lease)
                for alt in device_ids or []:
                    if device_key(alt) != device_key(device):
                        _write_json_atomic(lease_path(alt), lease)
                return lease
            remaining = deadline - _now()
            if remaining <= 0:
                raise LeaseConflict(
                    "device %s held by another controller: %s"
                    % (device, format_holder(existing)),
                    lease=existing,
                )
        # Sleep outside the lock so other waiters / holders can progress.
        time.sleep(min(2.0, remaining))


def heartbeat(
    device: str,
    *,
    session_id: str | None = None,
    ttl_sec: int | None = None,
) -> dict[str, Any] | None:
    """Extend expires_at if we own the lease. Returns updated lease or None."""
    lease = find_active_lease(device)
    if not lease or not ours(lease):
        return None
    if session_id and holder_session(lease) and holder_session(lease) != session_id:
        return None
    now = _now()
    ttl = int(ttl_sec or lease.get("ttl_sec") or DEFAULT_TTL_SEC)
    lease["heartbeat_at"] = _iso(now)
    lease["expires_at"] = _iso(now + ttl)
    # Write to the file we found + primary key.
    path = Path(lease.get("_path") or lease_path(device))
    clean = {k: v for k, v in lease.items() if not k.startswith("_")}
    _write_json_atomic(path, clean)
    if path != lease_path(device):
        _write_json_atomic(lease_path(device), clean)
    return clean


def release(
    device: str,
    *,
    session_id: str | None = None,
    force: bool = False,
) -> bool:
    """Clear lease if we own it (or force). Returns True if a file was removed."""
    removed = False
    want = {device_key(device), str(device).strip().lower()}
    targets: list[Path] = [lease_path(device)]
    for lease in list_leases(active_only=False):
        ids = lease_device_ids(lease)
        if not (ids & want):
            continue
        if not force and not ours(lease):
            continue
        if (
            not force
            and session_id
            and holder_session(lease)
            and holder_session(lease) != session_id
        ):
            continue
        p = Path(lease.get("_path") or lease_path(device))
        if p not in targets:
            targets.append(p)
        for alt in lease.get("device_ids") or []:
            ap = lease_path(str(alt))
            if ap not in targets:
                targets.append(ap)
    for p in targets:
        try:
            if not p.is_file():
                continue
            data = _read_json(p)
            if data and not force and not ours(data):
                continue
            if (
                data
                and not force
                and session_id
                and holder_session(data)
                and holder_session(data) != session_id
            ):
                continue
            p.unlink()
            removed = True
        except OSError:
            pass
    return removed


def status_lines(device: str | None = None) -> list[str]:
    lines: list[str] = []
    if device:
        lease = find_active_lease(device)
        if not lease:
            lines.append("%s: free (no active lease)" % device)
            return lines
        lines.append("%s: HELD %s" % (device, format_holder(lease)))
        return lines
    active = list_leases(active_only=True)
    if not active:
        lines.append("no active device screen-control leases")
        return lines
    for lease in active:
        d = lease.get("device") or "?"
        lines.append("%s: HELD %s" % (d, format_holder(lease)))
    return lines
