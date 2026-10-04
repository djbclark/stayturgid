# -*- coding: utf-8 -*-
"""Is the running Shizuku server older than the installed Shizuku APK?

`adb install -r` replaces the APK and kills the app's own processes, but the
server runs as uid shell and survives, still executing the old code. A new
server-side rule is then silently not in force (2026-10-04: p7a and t2 ran an
r2785 server for hours under an r2787 APK). The server is *stale* when it
started before the package's lastUpdateTime.

One probe, run as uid shell in a single `adb shell` call, measures both sides
on the phone's own clock and prints the verdict, so every consumer applies the
same rule:

- shizuku_start (deploy) restarts a stale server;
- device/termux/py/stayturgid_repair.py carries a byte-identical copy of the
  probe (it runs on the phone, where this collection is not installed);
- control/lib/fleet_health.py runs it inside HEALTH_GATHER for Mac visibility.

Measurement choices:

- Server start = boot time + /proc/<pid>/stat field 22 (start, in clock ticks
  since boot). Boot time is `date +%s` minus /proc/uptime, both read in the
  same call. `stat -c %Y /proc/<pid>` is not used: procfs stamps an inode when
  it is first instantiated (first lookup, or again after cache eviction), not
  when the process started, so it can read hours late. toybox `ps -o ETIME`
  needs parsing of [[dd-]hh:]mm:ss and has only second-level wall precision
  anyway.
- Package update = `dumpsys package` lastUpdateTime, a local-time string,
  converted by the phone's own `date` so its timezone (and that date's DST)
  applies. `pm list packages` / `cmd package` expose no timestamp.
- USER_HZ is fixed at 100 by the arm/arm64 ABI; `getconf CLK_TCK` is still
  preferred where toybox has it.

Anything unreadable, and any timestamp later than the phone's own "now",
yields "unknown", which never triggers a restart.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

SHIZUKU_PKG = "moe.shizuku.privileged.api"

# Covers the seconds-granularity of both clocks and the gap between reading
# uptime and date; small enough that a server started just before an install
# still counts as stale.
STALE_TOLERANCE_SEC = 30

STALE_YES = "yes"
STALE_NO = "no"
STALE_UNKNOWN = "unknown"

# One line, no single quotes: fleet_health embeds it in '...' for
# `adb shell`, and every caller sends it as one argv string to `sh -c`.
_PROBE_TEMPLATE = (
    'isnum() { case "$1" in ""|*[!0-9]*) return 1;; esac; return 0; }; '
    "now=$(date +%s); start=; upd=; "
    'p=$(pgrep -o -f "[s]hizuku_(plus_)?server"); '
    'if isnum "$p"; then '
    'ticks=$(cut -d " " -f 22 /proc/$p/stat 2>/dev/null); '
    "up=$(cat /proc/uptime 2>/dev/null); up=${up%%.*}; "
    'hz=$(getconf CLK_TCK 2>/dev/null); isnum "$hz" || hz=100; '
    'if isnum "$ticks" && isnum "$up" && isnum "$now" && [ "$hz" -gt 0 ]; then '
    "start=$((now - up + ticks / hz)); fi; "
    "fi; "
    't=$(dumpsys package @PKG@ 2>/dev/null | sed -n "s/^ *lastUpdateTime=//p" | head -n 1); '
    'if [ -n "$t" ]; then upd=$(date -d "$t" +%s 2>/dev/null || date -D "%Y-%m-%d %H:%M:%S" -d "$t" +%s 2>/dev/null); fi; '
    "v=unknown; "
    'if isnum "$start" && isnum "$upd" && isnum "$now" '
    '&& [ "$upd" -le $((now + @TOL@)) ] && [ "$start" -le $((now + @TOL@)) ]; then '
    'if [ $((start + @TOL@)) -lt "$upd" ]; then v=yes; else v=no; fi; '
    "fi; "
    'echo "shizuku_server_start=${start:-unknown}"; '
    'echo "shizuku_pkg_update=${upd:-unknown}"; '
    'echo "shizuku_server_stale=$v"'
)


def staleness_probe(pkg=SHIZUKU_PKG, tolerance=STALE_TOLERANCE_SEC):
    """The device-side probe as one `adb shell` command string."""
    return _PROBE_TEMPLATE.replace("@PKG@", pkg).replace("@TOL@", str(int(tolerance)))


def _epoch(raw):
    return int(raw) if raw and raw.isdigit() else None


def parse_staleness(output):
    """Probe output -> {"stale": yes|no|unknown, "server_start": int|None, "package_updated": int|None}."""
    fields = {}
    for line in (output or "").replace("\r", "").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep:
            fields[key] = value.strip()
    stale = fields.get("shizuku_server_stale")
    if stale not in (STALE_YES, STALE_NO):
        stale = STALE_UNKNOWN
    return {
        "stale": stale,
        "server_start": _epoch(fields.get("shizuku_server_start")),
        "package_updated": _epoch(fields.get("shizuku_pkg_update")),
    }
