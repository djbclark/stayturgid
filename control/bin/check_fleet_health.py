#!/usr/bin/env python3
"""Session triage for Mac fleet soft-health logs.

Agents: run at session start (and when the operator asks about fleet health).
If this exits non-zero, **tell the operator** — do not wait to be asked.

    python3 control/bin/check_fleet_health.py
    python3 control/bin/check_fleet_health.py --hours 6

Reads ~/.config/stayturgid/logs/fleet-health.log and state/fleet-health/.
Does not mutate devices. Exit 0 = clean; 1 = problems; 2 = no log / misconfig.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
LOG = ROOT / "logs" / "fleet-health.log"
ACCESS_LOG = ROOT / "logs" / "access-monitor.log"
ERROR_LOG = ROOT / "logs" / "errors.log"
STATE_DIR = ROOT / "state" / "fleet-health"
CONSECUTIVE_ALERT = 2

LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$"
)
SEVERITY_TOKENS = {
    "EMERG", "ALERT", "CRIT", "ERR", "WARNING", "NOTICE", "INFO", "DEBUG"
}


def parse_ts(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def scrape_rest(rest: str) -> str | None:
    """Strip optional 'via <path>: ' prefix; require a health scrape body."""
    body = rest
    if body.startswith("via "):
        # path has no spaces: "via adb:1.2.3.4:5555: sshd=ok ..."
        idx = body.find(": ")
        if idx == -1:
            return None
        body = body[idx + 2 :]
    if "issues=" not in body and "sshd=" not in body:
        return None
    return body


def record_host_and_rest(host: str, rest: str) -> tuple[str, str] | None:
    """Normalize legacy logs and newer logs that include a severity column."""
    if host in SEVERITY_TOKENS:
        fields = rest.split(None, 1)
        if len(fields) != 2:
            return None
        host, rest = fields
    return host, rest


def latest_per_host(log_path: Path, since: dt.datetime | None) -> dict[str, tuple[dt.datetime, str]]:
    """host -> (timestamp, scrape body) for last matching scrape."""
    out: dict[str, tuple[dt.datetime, str]] = {}
    if not log_path.is_file():
        return out
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        ts_s, host, rest = m.group(1), m.group(2), m.group(3)
        normalized = record_host_and_rest(host, rest)
        if normalized is None:
            continue
        host, rest = normalized
        if host in ("health",):
            continue
        body = scrape_rest(rest)
        if body is None:
            continue
        ts = parse_ts(ts_s)
        if ts is None:
            continue
        if since and ts < since:
            continue
        out[host] = (ts, body)
    return out


ISSUES_RE = re.compile(r"issues=([^\s]+)")


def read_consecutive() -> dict[str, int]:
    out: dict[str, int] = {}
    if not STATE_DIR.is_dir():
        return out
    for p in STATE_DIR.iterdir():
        if not p.is_file():
            continue
        try:
            out[p.name] = int(p.read_text().strip() or "0")
        except (OSError, ValueError):
            out[p.name] = 0
    return out


def issues_from_rest(rest: str) -> list[str]:
    m = ISSUES_RE.search(rest)
    if not m:
        return []
    raw = m.group(1)
    if raw in ("none", "?", ""):
        return []
    return [x for x in raw.split(",") if x]


def host_from_access_line(line: str) -> str | None:
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    normalized = record_host_and_rest(m.group(2), m.group(3))
    return normalized[0] if normalized else None


def partition_access_hits(
    hits: list[str], recovered_hosts: set[str]
) -> tuple[list[str], list[str]]:
    """Split access LOST lines: active (still alarming) vs historical (host ok now)."""
    active: list[str] = []
    historical: list[str] = []
    for line in hits:
        host = host_from_access_line(line)
        if host and host in recovered_hosts:
            historical.append(line)
        else:
            active.append(line)
    return active, historical


def ok_host_names(ok_hosts: list[str]) -> set[str]:
    names: set[str] = set()
    for line in ok_hosts:
        name = (line.split() or [""])[0]
        if name:
            names.add(name)
    return names


def recent_access_lost(hours: float) -> list[str]:
    if not ACCESS_LOG.is_file():
        return []
    since = dt.datetime.now() - dt.timedelta(hours=hours)
    hits: list[str] = []
    try:
        for line in ACCESS_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            if "LOST" in line or "unreachable on all paths (consecutive: 2)" in line:
                m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if not m:
                    continue
                ts = parse_ts(m.group(1))
                if ts and ts >= since:
                    hits.append(line.strip())
    except OSError:
        return []
    return hits[-5:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Only consider log lines newer than this many hours (default 24)",
    )
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Print nothing when healthy (still exit 0)",
    )
    args = ap.parse_args(argv)

    if not LOG.is_file():
        print(
            "ALERT: fleet-health.log missing at %s — launchd com.stayturgid.fleet-health "
            "may not be installed (run: ansible-playbook ansible/playbooks/control_node/agents.yml)"
            % LOG,
            file=sys.stderr,
        )
        return 2

    since = dt.datetime.now() - dt.timedelta(hours=args.hours)
    latest = latest_per_host(LOG, since)
    consec = read_consecutive()

    if not latest:
        print(
            "ALERT: no fleet-health scrapes in the last %.0fh — check launchd "
            "com.stayturgid.fleet-health and %s" % (args.hours, LOG),
            file=sys.stderr,
        )
        return 2

    problems: list[str] = []
    ok_hosts: list[str] = []
    currently_reachable: set[str] = set()
    for host in sorted(latest):
        ts, rest = latest[host]
        issues = issues_from_rest(rest)
        n = consec.get(host, 0)
        age_min = (dt.datetime.now() - ts).total_seconds() / 60.0
        stale_scrape = age_min > 20  # launchd is 5 min; >20 min = agent stuck
        if not stale_scrape:
            currently_reachable.add(host)
        if issues or n >= CONSECUTIVE_ALERT or stale_scrape:
            bits = ["%s" % host]
            if issues:
                bits.append("issues=%s" % ",".join(issues))
            else:
                bits.append("issues=none")
            bits.append("consecutive=%d" % n)
            bits.append("last=%.0fm ago" % age_min)
            if stale_scrape:
                bits.append("SCRAPE_STALE")
            problems.append(" ".join(bits) + " | " + rest)
        else:
            ok_hosts.append("%s (ok, last=%.0fm)" % (host, age_min))

    access_hits = recent_access_lost(args.hours)
    active_access, historical_access = partition_access_hits(
        access_hits, currently_reachable
    )

    if not problems and not active_access:
        if not args.quiet_ok:
            print("fleet-health: OK — %s" % (", ".join(ok_hosts) or "no hosts"))
            print("log: %s" % LOG)
            if historical_access:
                print("note: resolved access-monitor events (not counted):")
                for h in historical_access:
                    print("  • %s" % h)
        return 0

    print("=== fleet-health PROBLEMS (tell the operator) ===")
    print("log: %s" % LOG)
    for p in problems:
        print("  • %s" % p)
    if active_access:
        print("recent access-monitor LOST/unreachable@2:")
        for h in active_access:
            print("  • %s" % h)
    if historical_access:
        print("resolved access-monitor (host ok now — not counted):")
        for h in historical_access:
            print("  • %s" % h)
    if ok_hosts:
        print("ok: %s" % ", ".join(ok_hosts))
    print(
        "Next: prefer fixing AutoJs6/a11y/repair before OPTIONS 43–45; "
        "see docs/handoff.md § Mac fleet health."
    )
    # Show grouped device errors.  The raw errors.log is deliberately left
    # untouched for forensic detail; health output should stay triage-sized.
    if ERROR_LOG.is_file():
        entries = _read_device_error_entries(hours=args.hours)
        if entries:
            active_hosts = {p.split()[0] for p in problems}
            recovered_hosts = currently_reachable - active_hosts
            summaries = summarize_device_errors(entries, active_hosts, recovered_hosts)
            print("\n=== device error summary (%dh; raw detail in %s) ===" % (args.hours, ERROR_LOG))
            labels = {
                "active": "active device errors",
                "recovered": "recovered device errors (host healthy now)",
                "historical": "historical device errors (host not in current scrape)",
            }
            for category in ("active", "recovered", "historical"):
                rows = summaries[category]
                if not rows:
                    continue
                print("%s:" % labels[category])
                for detail, count, latest_ts in rows[:20]:
                    suffix = " (x%d, latest %s)" % (
                        count, latest_ts.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    print("  • %s%s" % (detail, suffix))
    return 1


def _read_device_error_entries(hours: float) -> list[tuple[dt.datetime, str, str]]:
    """Read recent device errors as ``(timestamp, host, message)`` tuples."""
    since = dt.datetime.now() - dt.timedelta(hours=hours)
    results: list[tuple[dt.datetime, str, str]] = []
    try:
        with open(ERROR_LOG) as f:
            for line in f:
                line = line.rstrip()
                m = LINE_RE.match(line)
                if not m:
                    continue
                ts_val = parse_ts(m.group(1))
                if ts_val and ts_val >= since:
                    rest = m.group(3).strip()
                    # errors.log normally has ``ERR host: ...`` while older
                    # entries may omit the severity column.
                    host = m.group(2)
                    if host in SEVERITY_TOKENS:
                        fields = rest.split(None, 1)
                        if len(fields) == 2:
                            host, rest = fields
                    if host.endswith(":"):
                        host = host[:-1]
                    nested = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+", rest)
                    if nested:
                        rest = rest[nested.end() :]
                    if rest:
                        results.append((ts_val, host, rest[:240]))
    except OSError:
        pass
    return results[-500:]


def _read_device_errors(hours: float) -> list[str]:
    """Compatibility view of recent errors; raw detail remains available in the log."""
    return ["%s %s: %s" % (ts.strftime("%Y-%m-%d %H:%M:%S"), host, message)
            for ts, host, message in _read_device_error_entries(hours)]


def summarize_device_errors(
    entries: list[tuple[dt.datetime, str, str]],
    active_hosts: set[str],
    recovered_hosts: set[str],
) -> dict[str, list[tuple[str, int, dt.datetime]]]:
    """Group repeated errors and classify them by current host health."""
    grouped: dict[str, Counter[tuple[str, str]]] = {
        "active": Counter(), "recovered": Counter(), "historical": Counter()
    }
    latest: dict[tuple[str, str], dt.datetime] = {}
    for ts, host, message in entries:
        category = "active" if host in active_hosts else (
            "recovered" if host in recovered_hosts else "historical"
        )
        key = (host, " ".join(message.split()))
        grouped[category][key] += 1
        latest[key] = max(ts, latest.get(key, ts))
    return {
        category: [
            ("%s: %s" % key[0:2], count, latest[key])
            for key, count in counts.most_common()
        ]
        for category, counts in grouped.items()
    }


if __name__ == "__main__":
    sys.exit(main())
