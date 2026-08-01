"""Long-term statistics — JSONL events kept forever (no 30-day rotation).

All stayturgid monitors and heal scripts should call record_event() for:
  - connection_path:   which transport was used for a probe
  - heal_triggered:     which self-heal fired
  - device_status:      online / offline transitions
  - issue_detected:     per-issue occurrence
  - soft_health:        full dual-run probe snapshot (agent_age, watchdog_age, port, …)
  - device_log_failure: an ERR/WARNING-severity line freshly seen in an
    on-device log (Termux ``watchdog.log`` or native-agent ``agent.log``)
    during a fleet-health SSH probe — fields: ``source`` (watchdog.log /
    agent.log), ``severity`` (ERR / WARNING), ``message`` (the raw log
    line, truncated). See ``control/lib/fleet_health.py``'s
    ``extract_devlog_lines()`` and
    ``control/bin/fleet_health_monitor.py``'s
    ``_report_device_log_failures()``.

Primary durable files under ``~/.config/stayturgid/stats/``:

  - ``events.jsonl`` — all event types (local query_events)
  - ``soft_health.jsonl`` — soft_health + device_log_failure, for Vector →
    OpenObserve (device_log_failure rides the same file/stream deliberately —
    Vector's file source only tails soft_health.jsonl, so dual-writing here
    reaches OpenObserve with zero Vector config changes; query by the
    ``type`` field to distinguish rows)

Writers use whole-line append + flush + fsync so a crash mid-write at worst
leaves one corrupt last line (Vector drops parse errors). Vector tails
``soft_health.jsonl`` with disk buffers and end-to-end acks so OpenObserve can
be down for days without data loss.

Query examples::

    from control.lib import stats
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = stats.query_events(since=since, event_type="soft_health", device="example-device")
"""

from __future__ import annotations

import datetime
import json
import os
from datetime import timezone
from pathlib import Path

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
STATS_DIR = ROOT / "stats"
EVENTS_JSONL = "events.jsonl"
SOFT_HEALTH_JSONL = "soft_health.jsonl"


def _ensure_dir() -> None:
    try:
        STATS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def soft_health_path() -> Path:
    """Path Vector tails. Create empty file so the file source can attach early."""
    _ensure_dir()
    path = STATS_DIR / SOFT_HEALTH_JSONL
    try:
        if not path.is_file():
            path.touch()
    except OSError:
        pass
    return path


def ts() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_jsonl_line(path: Path, event: dict) -> None:
    """Append one complete JSON line; fsync for crash durability.

    Never raises — soft-health must not break fleet_health_monitor.
    """
    try:
        line = json.dumps(event, sort_keys=True, default=str) + "\n"
    except (TypeError, ValueError):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Binary open avoids newline translation surprises; we control LF.
        with open(path, "ab", buffering=0) as f:
            f.write(line.encode("utf-8"))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync can fail on some FS; line is still on OS page cache.
                pass
    except OSError:
        pass


def record_event(event_type: str, device: str, **details: object) -> None:
    _ensure_dir()
    event: dict = {
        "ts": ts(),
        "type": event_type,
        "device": device,
    }
    # Coerce non-JSON-safe values defensively
    for k, v in details.items():
        if v is None:
            event[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            event[k] = v
        else:
            event[k] = str(v)

    _append_jsonl_line(STATS_DIR / EVENTS_JSONL, event)

    # Dedicated file for Vector micro-batch → OpenObserve stream soft_health.
    # Keeps OO ingest independent of other event types and easy to re-tail.
    # device_log_failure rides the same file (see module docstring) so it
    # reaches OpenObserve through the existing pipe with no new Vector config.
    if event_type in ("soft_health", "device_log_failure"):
        _append_jsonl_line(soft_health_path(), event)


def query_events(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    event_type: str | None = None,
    device: str | None = None,
) -> list[dict]:
    filepath = STATS_DIR / EVENTS_JSONL
    if not filepath.is_file():
        return []

    results: list[dict] = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    # Corrupt/partial line (crash mid-write) — skip, keep going.
                    continue

                if event_type and ev.get("type") != event_type:
                    continue
                if device and ev.get("device") != device:
                    continue

                ev_ts_s = ev.get("ts", "")
                try:
                    ev_ts = datetime.datetime.strptime(ev_ts_s, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=datetime.timezone.utc
                    )
                except (ValueError, TypeError):
                    continue

                if since and ev_ts < since:
                    continue
                if until and ev_ts > until:
                    continue

                ev["_parsed_ts"] = ev_ts
                results.append(ev)
    except OSError:
        pass

    return results


def aggregate_stats(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    devices: list[str] | None = None,
) -> dict:
    """Return a structured stats summary for the dashboard."""
    events = query_events(since=since, until=until)

    result: dict = {
        "total_events": len(events),
        "connection_paths": {},  # {"adb:...": 5, "ssh:...": 3}
        "heals": {},  # {"watchdog": 2, "repair": 1, "a11y": 0, ...}
        "device_status": {},  # {"oneui-device": {"online": 42, "offline": 3}, ...}
        "issues": {},  # {"watchdog_stale": 5, "bootloop_down": 3, ...}
        "devices_seen": set(),
        "time_range": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
    }

    for ev in events:
        dev = ev.get("device", "")
        if devices and dev not in devices:
            continue
        result["devices_seen"].add(dev)

        etype = ev.get("type", "")

        if etype == "connection_path":
            via = ev.get("via", "unknown")
            result["connection_paths"][via] = result["connection_paths"].get(via, 0) + 1

        elif etype == "heal_triggered":
            heal = ev.get("heal", "unknown")
            result["heals"][heal] = result["heals"].get(heal, 0) + 1

        elif etype == "device_status":
            if dev not in result["device_status"]:
                result["device_status"][dev] = {"online": 0, "offline": 0}
            status = ev.get("status", "unknown")
            if status in ("online", "offline"):
                result["device_status"][dev][status] += 1

        elif etype == "issue_detected":
            issue = ev.get("issue", "unknown")
            result["issues"][issue] = result["issues"].get(issue, 0) + 1

        elif etype == "soft_health":
            if "soft_health" not in result:
                result["soft_health"] = {
                    "samples": 0,
                    "agent_stale_samples": 0,
                    "agent_missing_samples": 0,
                    "port_closed_samples": 0,
                    "shizuku_down_samples": 0,
                }
            sh = result["soft_health"]
            sh["samples"] = int(sh["samples"]) + 1
            issues_s = str(ev.get("issues") or "")
            if "agent_stale" in issues_s:
                sh["agent_stale_samples"] = int(sh["agent_stale_samples"]) + 1
            if ev.get("agent_age") in ("missing", None, ""):
                sh["agent_missing_samples"] = int(sh["agent_missing_samples"]) + 1
            port = str(ev.get("port") or "")
            if port in ("CLOSED_NO_SHELL", "closed", "CLOSED"):
                sh["port_closed_samples"] = int(sh["port_closed_samples"]) + 1
            shizuku = str(ev.get("shizuku") or "").lower()
            if shizuku in ("down", "dead", "failed", "false", "0"):
                sh["shizuku_down_samples"] = int(sh["shizuku_down_samples"]) + 1

    result["devices_seen"] = sorted(result["devices_seen"])
    result["connection_paths"] = dict(sorted(result["connection_paths"].items(), key=lambda x: -x[1]))
    result["heals"] = dict(sorted(result["heals"].items(), key=lambda x: -x[1]))
    result["issues"] = dict(sorted(result["issues"].items(), key=lambda x: -x[1]))
    return result
