#!/usr/bin/env python3
"""Fetch one URL into a file. Exit 124 on the window, 1 on any other failure.

The obvious error is on stderr. A partial file is left for the next deploy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import asset_fetch  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--timeout", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        asset_fetch.fetch(args.url, args.dest, args.timeout)
    except asset_fetch.FetchError as exc:
        print(str(exc), file=sys.stderr)
        if "did not finish within" in str(exc):
            return 124
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
