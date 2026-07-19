#!/usr/bin/env python3
"""Cache and verify one pinned official otelcol-contrib artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


class ArtifactError(RuntimeError):
    """The collector artifact failed a supply-chain or architecture check."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise ArtifactError(f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}")


def normalize_device_arch(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"aarch64", "arm64"}:
        return "linux_arm64"
    raise ArtifactError(f"unsupported device architecture: {value!r}; expected aarch64/arm64")


def validate_linux_arm64_elf(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise ArtifactError(f"{path.name} is not an ELF executable")
    if header[4] != 2 or header[5] != 1:
        raise ArtifactError(f"{path.name} is not a 64-bit little-endian ELF executable")
    machine = struct.unpack("<H", header[18:20])[0]
    if machine != 183:  # EM_AARCH64
        raise ArtifactError(f"{path.name} ELF architecture is {machine}, expected AArch64 (183)")


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "stayturgid-otelcol-cache/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
            shutil.copyfileobj(response, out)
    except (OSError, urllib.error.URLError) as exc:
        raise ArtifactError(f"download failed for {url}: {exc}") from exc


def _extract_binary(archive: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = [member for member in bundle.getmembers() if member.name == "otelcol-contrib"]
            if len(members) != 1 or not members[0].isfile():
                raise ArtifactError("archive must contain exactly one regular otelcol-contrib file")
            source = bundle.extractfile(members[0])
            if source is None:
                raise ArtifactError("unable to read otelcol-contrib from archive")
            with destination.open("wb") as out:
                shutil.copyfileobj(source, out)
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactError(f"invalid collector archive: {exc}") from exc
    destination.chmod(0o755)


def _archive_binary_sha256(archive: Path) -> str:
    digest = hashlib.sha256()
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = [member for member in bundle.getmembers() if member.name == "otelcol-contrib"]
            if len(members) != 1 or not members[0].isfile():
                raise ArtifactError("archive must contain exactly one regular otelcol-contrib file")
            source = bundle.extractfile(members[0])
            if source is None:
                raise ArtifactError("unable to read otelcol-contrib from archive")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactError(f"invalid collector archive: {exc}") from exc
    return digest.hexdigest()


def ensure_cached(*, url: str, expected_sha256: str, cache_dir: Path, architecture: str) -> bool:
    if architecture != "linux_arm64":
        raise ArtifactError(f"unsupported archive architecture: {architecture!r}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_name = Path(urllib.parse.urlparse(url).path).name
    if not archive_name:
        raise ArtifactError("artifact URL has no archive filename")
    archive = cache_dir / archive_name
    binary = cache_dir / "otelcol-contrib"

    if archive.exists():
        verify_checksum(archive, expected_sha256)
    else:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{archive_name}.", dir=cache_dir)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            _download(url, temporary)
            verify_checksum(temporary, expected_sha256)
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)

    if binary.exists():
        validate_linux_arm64_elf(binary)
        if sha256_file(binary) != _archive_binary_sha256(archive):
            raise ArtifactError("cached otelcol-contrib binary does not match the verified archive")
        return False

    fd, temporary_name = tempfile.mkstemp(prefix=".otelcol-contrib.", dir=cache_dir)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        _extract_binary(archive, temporary)
        validate_linux_arm64_elf(temporary)
        os.replace(temporary, binary)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--architecture", required=True)
    args = parser.parse_args(argv)
    try:
        changed = ensure_cached(
            url=args.url,
            expected_sha256=args.sha256,
            cache_dir=args.cache_dir.expanduser(),
            architecture=args.architecture,
        )
    except ArtifactError as exc:
        parser.error(str(exc))
    print(json.dumps({"binary": str(args.cache_dir / "otelcol-contrib"), "changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
