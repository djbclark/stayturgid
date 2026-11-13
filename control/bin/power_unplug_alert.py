#!/usr/bin/env python3
"""Play the battery "locate me" chime for 2 seconds when this Mac loses wall power.

Same clip the Android battery alarm uses (device/termux/assets/battery-colors/locate.mp3,
made by control/tools/gen_locate_sound.py), so one sound means "a battery needs attention".

Long-running launchd agent (com.stayturgid.power-unplug-alert, KeepAlive). It blocks on the
darwin notification macOS posts whenever the power source changes (`notifyutil -1 -w`), so it
uses no CPU and does not poll. On each wake it reads `pmset -g ps`; only an AC -> Battery
transition rings. Plugging in, a charge-level tick, or a duplicate notification do not.

    control/bin/power_unplug_alert.py            run the watcher (what launchd runs)
    control/bin/power_unplug_alert.py --test     play the 2 s alert once and exit
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOUND_FILE = ROOT / "device/termux/assets/battery-colors/locate.mp3"
ALERT_SEC = 2
NOTIFY_KEY = "com.apple.system.powersources.source"
# macOS can post the key a few times for one unplug; a ring inside this window is a duplicate.
MIN_GAP_SEC = 5.0


def parse_source(out: str) -> str | None:
    """`pmset -g ps` -> "ac", "battery", or None when the source is not recognised."""
    if "'AC Power'" in out:
        return "ac"
    if "'Battery Power'" in out:
        return "battery"
    return None


def power_source() -> str | None:
    try:
        out = subprocess.run(["pmset", "-g", "ps"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_source(out)


def should_ring(prev: str | None, now: str | None, last_ring: float, t: float) -> bool:
    return prev == "ac" and now == "battery" and (t - last_ring) >= MIN_GAP_SEC


def ring(sound: Path = SOUND_FILE, secs: int = ALERT_SEC) -> bool:
    if not sound.exists():
        print("power_unplug_alert: no %s; alert skipped" % sound, file=sys.stderr)
        return False
    try:
        _ = subprocess.run(["afplay", "-t", str(secs), str(sound)], timeout=secs + 10, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print("power_unplug_alert: afplay failed: %s" % e, file=sys.stderr)
        return False
    return True


def wait_for_change() -> None:
    """Block until macOS posts a power-source change; an error just backs off."""
    r = subprocess.run(["notifyutil", "-1", "-w", NOTIFY_KEY], capture_output=True, check=False)
    if r.returncode != 0:
        time.sleep(5)


def watch() -> int:
    prev = power_source()
    last_ring = float("-inf")
    while True:
        wait_for_change()
        now = power_source()
        t = time.monotonic()
        if should_ring(prev, now, last_ring, t):
            _ = ring()
            last_ring = t
        if now is not None:
            prev = now


def main(argv: list[str]) -> int:
    if argv[1:] == ["--test"]:
        return 0 if ring() else 1
    if len(argv) > 1:
        print(__doc__)
        return 2
    return watch()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
