#!/usr/bin/env python3
"""Play the battery locate sound on one or more fleet devices, to find them by ear.

    control/bin/ring_device.py t2e          # ~30 s
    control/bin/ring_device.py all          # all Android devices in devices.conf, ~30 s
    control/bin/ring_device.py s24,t2e 45   # list of devices, ~45 s
    just ring t2e

Rings regardless of quiet hours and the phone's DND/silent setting (an explicit ask).
Stops automatically if the power button is pressed to turn the screen on, or from the
device's "Stop sound" notification button.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import subprocess
import sys

_LIB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from stayturgid_device import SSH_OPTS, iter_devices_conf  # noqa: E402

DEFAULT_SECS = 30


def parse_args(argv: list[str], conf_path: str | None = None) -> tuple[list[str], int, bool]:
    """Return ``(hosts, secs, is_all)`` from CLI args. Raises ValueError on bad input."""
    if not argv:
        raise ValueError("missing device target")
    if len(argv) > 1 and argv[-1].isdigit():
        secs = int(argv[-1])
        raw_targets = argv[:-1]
    else:
        secs = DEFAULT_SECS
        raw_targets = argv

    tokens: list[str] = []
    for item in raw_targets:
        for part in re.split(r"[,\s]+", item.strip()):
            if part:
                tokens.append(part)
    if not tokens:
        raise ValueError("missing device target")

    is_all = any(t.lower() == "all" for t in tokens)
    hosts: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t.lower() == "all":
            for name, *_rest in iter_devices_conf(conf_path):
                if name not in seen:
                    seen.add(name)
                    hosts.append(name)
        elif t not in seen:
            seen.add(t)
            hosts.append(t)

    if not hosts:
        raise ValueError("no Android devices found in devices.conf")
    return hosts, secs, is_all


def ring_host(host: str, secs: int) -> tuple[str, int, str]:
    """Trigger `stayturgid_battery_alarm.py ring <secs>` on *host* over SSH."""
    cmd = [
        "ssh",
        *SSH_OPTS,
        "-o",
        "ConnectTimeout=5",
        host,
        "python ~/.stayturgid/bin/stayturgid_battery_alarm.py ring %d" % secs,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        err = (r.stderr or r.stdout or "").strip()
        return host, r.returncode, err
    except subprocess.TimeoutExpired:
        return host, 124, "ssh timed out"
    except OSError as exc:
        return host, 1, str(exc)


def main(argv: list[str], conf_path: str | None = None) -> int:
    try:
        hosts, secs, is_all = parse_args(argv, conf_path=conf_path)
    except ValueError as exc:
        print("Error: %s\n\n%s" % (exc, __doc__.strip()), file=sys.stderr)
        return 2

    if len(hosts) == 1:
        results = [ring_host(hosts[0], secs)]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
            results = list(pool.map(lambda h: ring_host(h, secs), hosts))

    ok = 0
    for host, rc, err in results:
        if rc == 0:
            ok += 1
            print("%s: ringing for %ds" % (host, secs))
        else:
            detail = " (%s)" % err if err else ""
            print("%s: failed (rc=%d)%s" % (host, rc, detail), file=sys.stderr)

    if ok == 0:
        return 1
    if not is_all and ok < len(hosts):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
