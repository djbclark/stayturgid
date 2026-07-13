"""Long-term statistics — JSONL events kept forever (no 30-day rotation).

All stayturgid monitors and heal scripts should call record_event() for:
  - connection_path:  which transport was used for a probe
  - heal_triggered:   which self-heal fired
  - device_status:    online / offline transitions
  - issue_detected:   per-issue occurrence

Events are written as one JSON object per line to ~/.config/stayturgid/stats/.
"""
from __future__ import annotations

import datetime
import json
import os
from datetime import timezone
from pathlib import Path

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
STATS_DIR = ROOT / "stats"


def _ensure_dir() -> None:
    try:
        STATS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def ts() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_event(event_type: str, device: str, **details: str | int | float) -> None:
    _ensure_dir()
    event: dict = {
        "ts": ts(),
        "type": event_type,
        "device": device,
    }
    event.update(details)
    filepath = STATS_DIR / "events.jsonl"
    try:
        with open(filepath, "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        pass


def query_events(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    event_type: str | None = None,
    device: str | None = None,
) -> list[dict]:
    filepath = STATS_DIR / "events.jsonl"
    if not filepath.is_file():
        return []

    results: list[dict] = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event_type and ev.get("type") != event_type:
                    continue
                if device and ev.get("device") != device:
                    continue

                ev_ts_s = ev.get("ts", "")
                try:
                    ev_ts = datetime.datetime.strptime(
                        ev_ts_s, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc)
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
        "connection_paths": {},    # {"adb:...": 5, "ssh:...": 3}
        "heals": {},                # {"watchdog": 2, "repair": 1, "a11y": 0, ...}
        "device_status": {},        # {"s24": {"online": 42, "offline": 3}, ...}
        "issues": {},               # {"watchdog_stale": 5, "bootloop_down": 3, ...}
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

    result["devices_seen"] = sorted(result["devices_seen"])
    result["connection_paths"] = dict(sorted(
        result["connection_paths"].items(), key=lambda x: -x[1]
    ))
    result["heals"] = dict(sorted(
        result["heals"].items(), key=lambda x: -x[1]
    ))
    result["issues"] = dict(sorted(
        result["issues"].items(), key=lambda x: -x[1]
    ))

    return result
