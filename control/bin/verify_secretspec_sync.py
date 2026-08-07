#!/usr/bin/env python3
"""Fail-closed verification that the SecretSpec source and vault agree."""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from pathlib import Path

NAMES = (".env", "secretspec.toml")


def _regular_private(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(source_dir: Path, vault_dir: Path) -> list[str]:
    errors: list[str] = []
    try:
        vault_mode = stat.S_IMODE(vault_dir.lstat().st_mode)
    except FileNotFoundError:
        return [f"vault missing: {vault_dir}"]
    if not stat.S_ISDIR(vault_dir.lstat().st_mode) or vault_mode != 0o700:
        errors.append(f"vault must be a real 0700 directory: {vault_dir}")
    for name in NAMES:
        source = source_dir / name
        vault = vault_dir / name
        if not _regular_private(source):
            errors.append(f"source must be a real 0600 file: {source}")
            continue
        if not _regular_private(vault):
            errors.append(f"vault must be a real 0600 file: {vault}")
            continue
        if _digest(source) != _digest(vault):
            errors.append(f"hash mismatch: {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("vault_dir", type=Path)
    args = parser.parse_args(argv)
    errors = verify(args.source_dir, args.vault_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("SecretSpec source/vault hashes and permissions match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
