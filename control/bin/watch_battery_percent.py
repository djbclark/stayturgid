#!/usr/bin/env python3
"""Evidence-capture diagnostic for issue #16 (p7a battery-% status bar reset).

This is intentionally **not** a fix. Prior investigation (#16, #41, #42;
see docs/STATUS.md and PR #136) was exhaustive: every `settings put` call in
this repo (Ansible modules, Termux repair/presence/screen-control scripts,
Mac-side control/lib, and the native-agent CatastrophicRepair path) was
audited and none targets `status_bar_show_battery_percent` or any
namespace-wide reset. A live `just deploy p7a` recheck on 2026-08-01 held
the value unchanged throughout. So there is currently no known stayturgid
code path to fix, and guessing at one would risk masking the real cause.

What *was* missing from every past investigation: attribution. Nothing
captured *which* process touched the setting at the moment it changed. This
script implements the next step the last investigation recommended —
snapshot the value and `dumpsys settings` state immediately before/after a
specific stayturgid command, so a future recurrence leaves durable evidence
instead of just "it changed again".

Usage:
  control/bin/watch_battery_percent.py <host> -- <command...>

Example:
  control/bin/watch_battery_percent.py p7a -- just deploy hosts=p7a

Writes a JSON evidence record to artifacts/battery-percent-watch/, and exits
with the wrapped command's return code (0/1 changed-state is only reported,
never turned into a failure — this tool must never block a real deploy).
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import stayturgid_device as dev  # noqa: E402

NAMESPACE = "system"
KEY = "status_bar_show_battery_percent"
OUT_DIR = REPO / "artifacts" / "battery-percent-watch"

# `dumpsys settings` historical-operations lines vary by Android version/OEM
# (e.g. "12-31 09:00:00.123 UPDATE system:status_bar_show_battery_percent
# value=0 default=null ... pkg=com.android.shell"). Permissive by design —
# this augments the raw capture, it does not replace it.
_HISTORY_LINE_RE = re.compile(
    r"(?P<op>UPDATE|INSERT|DELETE)\s+\S*:?\S*"
    r".*?\bpkg=(?P<pkg>[\w.]+)",
    re.IGNORECASE,
)


def parse_setting_value(raw):
    """Normalize `settings get` output: strip, map the "null" sentinel to None."""
    if raw is None:
        return None
    value = raw.strip()
    if value == "" or value.lower() == "null":
        return None
    return value


def battery_percent_hidden(value):
    """True if the setting is in the "hidden" (bug-reproduced) state."""
    return value in (None, "0")


def extract_dumpsys_attribution(dumpsys_text, namespace=NAMESPACE, key=KEY):
    """Best-effort attribution for one settings row from `dumpsys settings`
    output. Returns [] (never raises) when the historical-operations
    section is absent or the format doesn't match — the raw dumpsys capture
    saved alongside this is the fallback evidence."""
    hits = []
    if not dumpsys_text:
        return hits
    needle = "%s:%s" % (namespace, key)
    for line in dumpsys_text.splitlines():
        if needle not in line:
            continue
        match = _HISTORY_LINE_RE.search(line)
        hits.append(
            {
                "line": line.strip(),
                "op": match.group("op").upper() if match else None,
                "pkg": match.group("pkg") if match else None,
            }
        )
    return hits


def build_evidence_record(host, command, before, after, dumpsys_before, dumpsys_after):
    changed = before != after
    return {
        "host": host,
        "command": list(command),
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "namespace": NAMESPACE,
        "key": KEY,
        "before": before,
        "after": after,
        "changed": changed,
        "reset_to_hidden": changed and battery_percent_hidden(after),
        "attribution_before": extract_dumpsys_attribution(dumpsys_before),
        "attribution_after": extract_dumpsys_attribution(dumpsys_after),
    }


def _adb(serial, *args, timeout=20):
    return subprocess.run(
        [dev.adb_bin(), "-s", serial, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _get_value(serial):
    result = _adb(serial, "settings", "get", NAMESPACE, KEY)
    return parse_setting_value(result.stdout)


def _get_dumpsys(serial):
    result = _adb(serial, "dumpsys", "settings", timeout=30)
    return result.stdout or ""


def main(argv):
    if "--" not in argv:
        print(__doc__)
        return 2
    sep = argv.index("--")
    host_args, command = argv[:sep], argv[sep + 1 :]
    if len(host_args) != 1 or not command:
        print(__doc__)
        return 2
    host = host_args[0]

    serial = dev.resolve_adb(host)

    before = _get_value(serial)
    dumpsys_before = _get_dumpsys(serial)
    print("[watch-battery-percent] before=%r — running: %s" % (before, " ".join(command)))

    rc = subprocess.call(command)

    after = _get_value(serial)
    dumpsys_after = _get_dumpsys(serial)

    record = build_evidence_record(host, command, before, after, dumpsys_before, dumpsys_after)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_path = OUT_DIR / ("%s-%s.json" % (host, ts))
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    if record["changed"]:
        print(
            "[watch-battery-percent] CHANGED: %r -> %r — evidence saved to %s (attach to issue #16)"
            % (before, after, out_path),
            file=sys.stderr,
        )
    else:
        print("[watch-battery-percent] unchanged (%r) — evidence saved to %s" % (before, out_path))

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
