"""Shared logging utilities: syslog severity levels, rotation, and error scraping.

All stayturgid components should use these conventions:

  Severity format:                     TIMESTAMP [TAG] LEVEL: message
  Rotation:                            Lines older than 30 days are pruned on trim.
  Error scraping (remote logs):        scrape_errors() detects severity from text patterns.

Usage:
  from control.lib.logging import log, ERR, WARNING, NOTICE, INFO, DEBUG

  log("fleet-health.log", INFO, "p7a via ssh: sshd=ok")
  log("fleet-health.log", ERR, "p7a port 5555 CLOSED — escalate to reboot")
"""
from __future__ import annotations

import datetime
import fcntl
import os
import re
import time
from pathlib import Path
from typing import Any

# ── Syslog severity levels ──────────────────────────────────────────────────
EMERG   = 0   # system is unusable
ALERT   = 1   # action must be taken immediately
CRIT    = 2   # critical conditions
ERR     = 3   # error conditions
WARNING = 4   # warning conditions
NOTICE  = 5   # normal but significant
INFO    = 6   # informational
DEBUG   = 7   # debug-level

_SEVERITY_LABELS: dict[int, str] = {
    EMERG:   "EMERG",
    ALERT:   "ALERT",
    CRIT:    "CRIT",
    ERR:     "ERR",
    WARNING: "WARNING",
    NOTICE:  "NOTICE",
    INFO:    "INFO",
    DEBUG:   "DEBUG",
}

# Compat aliases (lowercase, common aliases)
ERROR = ERR
WARN = WARNING


def severity_label(level: int) -> str:
    return _SEVERITY_LABELS.get(level, "UNKNOWN")


# ── Timestamp ────────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Core logging ─────────────────────────────────────────────────────────────
def _resolve_log_path(path_or_name: str) -> str:
    if path_or_name.startswith("/") or path_or_name.startswith("~"):
        return os.path.expanduser(path_or_name)
    return os.path.join(
        os.path.expanduser("~"), ".config", "stayturgid", "logs", path_or_name,
    )


def log(path_or_name: str, level: int, msg: str, *, also_print: bool = False) -> None:
    """Append a timestamped, severity-leveled line to a log file.

    Automatically creates parent directories.
    """
    path = _resolve_log_path(path_or_name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return

    line = "%s  %s %s\n" % (ts(), severity_label(level), msg)
    try:
        with open(path, "a") as f:
            f.write(line)
    except OSError:
        return

    if also_print:
        print(line.rstrip())


# ── Rotation / trimming ──────────────────────────────────────────────────────
_EXTRACT_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")


def _parse_ts(line: str) -> float | None:
    m = _EXTRACT_TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(
            m.group(1), "%Y-%m-%d %H:%M:%S",
        ).timestamp()
    except ValueError:
        return None


def trim_old_lines(path: str, max_age_days: int = 30, *, keep: int = 500) -> int:
    """Remove lines older than max_age_days. Falls back to line-count trim.

    Returns number of lines removed.
    """
    path = os.path.expanduser(path) if path.startswith("~") else path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return 0

    lock_path = path + ".lock"
    try:
        with open(lock_path, "a") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                with open(path) as f:
                    lines = f.readlines()
            except OSError:
                return 0

            cutoff = time.time() - (max_age_days * 86400)
            kept: list[str] = []
            removed = 0
            kept_with_age = 0

            for line in lines:
                ts_val = _parse_ts(line)
                if ts_val is not None and ts_val < cutoff:
                    removed += 1
                else:
                    kept.append(line)
                    if ts_val is not None:
                        kept_with_age += 1

            if removed > 0:
                with open(path, "w") as f:
                    f.writelines(kept)
            return removed
    except (OSError, ValueError):
        return 0


def trim_to_lines(path: str, max_lines: int) -> int:
    """Keep at most max_lines most recent lines."""
    path = os.path.expanduser(path) if path.startswith("~") else path
    lock_path = path + ".lock"
    try:
        with open(lock_path, "a") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                with open(path) as f:
                    lines = f.readlines()
            except OSError:
                return 0

            if len(lines) <= max_lines:
                return 0

            kept = lines[-max_lines:]
            with open(path, "w") as f:
                f.writelines(kept)
            return len(lines) - max_lines
    except (OSError, ValueError):
        return 0


def trim_log(path: str, *, max_age_days: int = 30, max_lines: int = 4000) -> tuple[int, int]:
    """Combined rotation: age-based prune + line-count cap.

    Returns (age_removed, line_removed) counts.
    """
    age_removed = trim_old_lines(path, max_age_days=max_age_days)
    line_removed = trim_to_lines(path, max_lines=max_lines)
    return age_removed, line_removed


# ── Error scraping from device logs ──────────────────────────────────────────
_ERROR_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bFATAL\b", re.I), CRIT),
    (re.compile(r"\bFAILED\b", re.I), ERR),
    (re.compile(r"\bCLOSED_NO_SHELL\b"), ERR),
    (re.compile(r"\bError\b"), ERR),
    (re.compile(r"\bException\b"), ERR),
    (re.compile(r"\bTraceback\b"), ERR),
    (re.compile(r"\bSecurityException\b"), ERR),
    (re.compile(r"\bCannot find function\b", re.I), ERR),
    (re.compile(r"\bcrash(?:ed|ing)?\b", re.I), ERR),
    (re.compile(r"\bpermission denied\b", re.I), WARNING),
    (re.compile(r"\btimeout\b", re.I), WARNING),
    (re.compile(r"\bstale\b", re.I), WARNING),
    (re.compile(r"\bMISSING\b"), NOTICE),
    (re.compile(r"\bskipped\b", re.I), INFO),
]

_REPAIR_LOG_GREP = (
    r"""export PATH=/data/data/com.termux/files/usr/bin:$PATH
l1=""; l2=""; [ -f ~/.stayturgid/logs/repair.log ] && l1="repair.log"; \
[ -f /sdcard/stayturgid/logs/watchdog.log ] && l2="watchdog.log"
grep -h -i -E 'FAILED|CLOSED_NO_SHELL|Error|Exception|Traceback|cannot find|crash|permission' \
  ${l1:+"~/.stayturgid/logs/repair.log"} \
  ${l2:+/sdcard/stayturgid/logs/watchdog.log} 2>/dev/null | tail -100
"""
)


def scrape_errors(text: str) -> list[tuple[int, str]]:
    """Parse a block of log text and extract error lines with severity levels.

    Returns list of (severity_level, line) tuples, sorted by severity (most severe first).
    """
    results: list[tuple[int, str]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern, level in _ERROR_PATTERNS:
            if pattern.search(line):
                dedup = (level, line[-200:])
                if dedup not in seen:
                    seen.add(dedup)
                    results.append((level, line))
                break

    results.sort(key=lambda x: (x[0], x[1]))
    return results
