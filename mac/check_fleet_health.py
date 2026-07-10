#!/usr/bin/env python3
"""Session triage for Mac fleet soft-health logs.

Agents: run at session start (and when the operator asks about fleet health).
If this exits non-zero, **tell the operator** — do not wait to be asked.

    python3 mac/check_fleet_health.py
    python3 mac/check_fleet_health.py --hours 6

Reads ~/.config/stayturgid/logs/fleet-health.log and state/fleet-health/.
Does not mutate devices. Exit 0 = clean; 1 = problems; 2 = no log / misconfig.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

_MAC = Path(__file__).resolve().parent
if str(_MAC) not in sys.path:
    sys.path.insert(0, str(_MAC))
from gui_audit import apply_gui_audit_overrides, load_gui_audit_overrides  # noqa: E402

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
LOG = ROOT / "logs" / "fleet-health.log"
ACCESS_LOG = ROOT / "logs" / "access-monitor.log"
GUI_AUDIT_LOG = ROOT / "logs" / "gui-audit.log"
STATE_DIR = ROOT / "state" / "fleet-health"
CONSECUTIVE_ALERT = 2
# GUI audit runs once nightly; treat scrapes older than this as stale (not alert).
GUI_AUDIT_FRESH_HOURS = 36.0

LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$"
)
# gui-audit.log: "2026-07-09 03:14:01  s24 done issues=aurora_filter_fdroid_off …"
GUI_DONE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+done\s+issues=([^\s]+)"
)


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


def latest_gui_audit(
    log_path: Path, since: dt.datetime | None
) -> dict[str, tuple[dt.datetime, list[str]]]:
    """host -> (timestamp, issue tags) from last 'done issues=' line per host."""
    out: dict[str, tuple[dt.datetime, list[str]]] = {}
    if not log_path.is_file():
        return out
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = GUI_DONE_RE.match(line.strip())
        if not m:
            continue
        ts = parse_ts(m.group(1))
        if ts is None:
            continue
        if since and ts < since:
            continue
        host = m.group(2)
        raw = m.group(3)
        issues = [] if raw in ("none", "?", "") else [x for x in raw.split(",") if x]
        out[host] = (ts, issues)
    return out


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
            "may not be installed (run: ansible-playbook ansible/playbooks/mac.yml)"
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
    for host in sorted(latest):
        ts, rest = latest[host]
        issues = issues_from_rest(rest)
        n = consec.get(host, 0)
        age_min = (dt.datetime.now() - ts).total_seconds() / 60.0
        stale_scrape = age_min > 20  # launchd is 5 min; >20 min = agent stuck
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

    gui_since = dt.datetime.now() - dt.timedelta(hours=GUI_AUDIT_FRESH_HOURS)
    gui_latest = latest_gui_audit(GUI_AUDIT_LOG, gui_since)
    gui_overrides = load_gui_audit_overrides()
    gui_problems: list[str] = []
    for host in sorted(gui_latest):
        gts, gissues = gui_latest[host]
        gissues, _ = apply_gui_audit_overrides(host, gissues, gui_overrides)
        if not gissues:
            continue
        age_h = (dt.datetime.now() - gts).total_seconds() / 3600.0
        gui_problems.append(
            "%s issues=%s last=%.1fh ago | gui-audit"
            % (host, ",".join(gissues), age_h)
        )

    if not problems and not access_hits and not gui_problems:
        if not args.quiet_ok:
            print("fleet-health: OK — %s" % (", ".join(ok_hosts) or "no hosts"))
            print("log: %s" % LOG)
            if gui_latest:
                print(
                    "gui-audit: OK — %s (log: %s)"
                    % (
                        ", ".join(
                            "%s (issues=none)" % h for h in sorted(gui_latest)
                        ),
                        GUI_AUDIT_LOG,
                    )
                )
        return 0

    print("=== fleet-health PROBLEMS (tell the operator) ===")
    print("log: %s" % LOG)
    for p in problems:
        print("  • %s" % p)
    if access_hits:
        print("recent access-monitor LOST/unreachable@2:")
        for h in access_hits:
            print("  • %s" % h)
    if gui_problems:
        print("gui-audit gaps (H2-style; log: %s):" % GUI_AUDIT_LOG)
        for g in gui_problems:
            print("  • %s" % g)
    if ok_hosts:
        print("ok: %s" % ", ".join(ok_hosts))
    print(
        "Next: prefer fixing AutoJs6/a11y/repair before OPTIONS 43–45; "
        "GUI gaps → mac/gui_audit.py / configure_aurora; "
        "see HANDOFF.md § Mac fleet health."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
