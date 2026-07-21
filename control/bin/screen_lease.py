#!/usr/bin/env python3
"""CLI for cross-project device screen-control leases (DSCL v1).

Usage:
  python3 control/bin/screen_lease.py status [device]
  python3 control/bin/screen_lease.py check <device>
  python3 control/bin/screen_lease.py acquire <device> [--purpose TEXT]
  python3 control/bin/screen_lease.py release <device>
  python3 control/bin/screen_lease.py heartbeat <device>

Exit codes:
  0 — free / success
  1 — held by another project (check)
  2 — usage / error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import device_screen_lease as dsl
import stayturgid_device as dev


def _ids(device: str) -> list[str]:
    ids = [device]
    try:
        serial = dev.resolve_adb(device)
        if serial and serial != device:
            ids.append(serial)
        row = dev.device_row(device)
        if row:
            usb, ts_ip, lan = row
            if usb and usb != "-":
                ids.append(usb)
            if ts_ip and ts_ip != "-":
                ids.append("%s:5555" % ts_ip)
            if lan and lan != "-":
                ids.append("%s:5555" % lan)
    except Exception:
        pass
    return ids


def cmd_status(device: str | None) -> int:
    for line in dsl.status_lines(device):
        print(line)
    print("store: %s" % dsl.leases_dir())
    return 0


def cmd_check(device: str) -> int:
    lease = dsl.find_active_lease(device, *(_ids(device)))
    if not lease:
        print("%s: free" % device)
        return 0
    print("%s: HELD %s" % (device, dsl.format_holder(lease)))
    print(json.dumps({k: v for k, v in lease.items() if not str(k).startswith("_")}, indent=2))
    if dsl.ours(lease):
        print("(held by this project — safe to renew)")
        return 0
    return 1


def cmd_acquire(device: str, purpose: str) -> int:
    try:
        lease = dsl.acquire(
            device,
            device_ids=_ids(device),
            purpose=purpose,
            agent=dsl.agent_id(),
        )
    except dsl.LeaseConflict as e:
        print("CONFLICT: %s" % e, file=sys.stderr)
        if e.lease:
            print(
                json.dumps(
                    {k: v for k, v in e.lease.items() if not str(k).startswith("_")},
                    indent=2,
                ),
                file=sys.stderr,
            )
        return 1
    print(json.dumps(lease, indent=2))
    return 0


def cmd_release(device: str) -> int:
    ok = dsl.release(device)
    print("released=%s device=%s" % (ok, device))
    return 0 if ok else 1


def cmd_heartbeat(device: str) -> int:
    lease = dsl.heartbeat(device)
    if not lease:
        print("no lease to heartbeat for %s" % device, file=sys.stderr)
        return 1
    print(json.dumps(lease, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_st = sub.add_parser("status", help="List active leases")
    p_st.add_argument("device", nargs="?", default=None)

    p_ck = sub.add_parser("check", help="Check one device (exit 1 if foreign hold)")
    p_ck.add_argument("device")

    p_ac = sub.add_parser("acquire", help="Acquire lease")
    p_ac.add_argument("device")
    p_ac.add_argument("--purpose", default="manual")

    p_rel = sub.add_parser("release", help="Release our lease")
    p_rel.add_argument("device")

    p_hb = sub.add_parser("heartbeat", help="Extend our lease")
    p_hb.add_argument("device")

    args = ap.parse_args(argv)
    if args.cmd == "status":
        return cmd_status(args.device)
    if args.cmd == "check":
        return cmd_check(args.device)
    if args.cmd == "acquire":
        return cmd_acquire(args.device, args.purpose)
    if args.cmd == "release":
        return cmd_release(args.device)
    if args.cmd == "heartbeat":
        return cmd_heartbeat(args.device)
    return 2


if __name__ == "__main__":
    sys.exit(main())
