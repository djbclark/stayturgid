#!/usr/bin/env python3
"""Configure or check the two optional system Homebrew PATH files on macOS."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

FILES = {
    Path("/etc/paths.d/homebrew"): "/opt/homebrew/bin\n/opt/homebrew/sbin\n",
    Path("/etc/ssh/sshd_config.d/50-stayturgid-homebrew-path.conf"): (
        "# stayturgid: expose Homebrew tools to noninteractive SSH sessions.\n"
        "# This affects command execution on the Mac, including ET's remote etterminal.\n"
        "SetEnv PATH=/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n"
    ),
}


def matches() -> bool:
    for path, expected in FILES.items():
        try:
            if path.read_text(encoding="utf-8") != expected:
                return False
        except OSError:
            return False
    return True


def write_atomic(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.chown(temporary, 0, 0)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args()
    if args.check:
        print("system Homebrew PATH: configured" if matches() else "WARNING: system Homebrew PATH absent or drifted")
        return 0 if matches() else 1
    if os.geteuid() != 0:
        parser.error("must be run through sudo")
    for path, content in FILES.items():
        if not path.parent.is_dir():
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            write_atomic(path, content)
    print("system Homebrew PATH: configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
