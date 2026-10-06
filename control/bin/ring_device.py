#!/usr/bin/env python3
"""Play the battery locate sound on a fleet device, to find it by ear.

    control/bin/ring_device.py s24        # ~60 s
    control/bin/ring_device.py hd8 120    # ~120 s
    just ring s24

Rings regardless of quiet hours and the phone's DND/silent setting (an explicit ask).
Stop it from the device's "Stop sound" notification button. Hermes can run this when
asked to ring a phone.
"""

import subprocess
import sys


def main(argv):
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    host, secs = argv[0], int(argv[1]) if len(argv) > 1 else 60
    r = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            host,
            "python ~/stayturgid_battery_alarm.py ring %d" % secs,
        ],
        timeout=60,
    )
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
