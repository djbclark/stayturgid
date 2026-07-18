#!/usr/bin/env python3
"""CLI for stayturgid ADB target resolution (USB when plugged in, else wireless).

Usage:
  resolve_adb.py oneui-device
  resolve_adb.py --ssh-host oneui-device
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import stayturgid_device as dev  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve stayturgid ADB target")
    parser.add_argument("alias", help="Device alias, USB serial, or host:port")
    parser.add_argument(
        "--ssh-host",
        action="store_true",
        help="Print SSH config Host alias (empty when unknown)",
    )
    parser.add_argument(
        "--conf",
        default=None,
        help="Override devices.conf path (default: ~/.config/stayturgid/devices.conf)",
    )
    args = parser.parse_args(argv)

    if args.ssh_host:
        print(dev.resolve_ssh_host(args.alias, args.conf))
        return 0

    print(dev.resolve_adb(args.alias, args.conf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
