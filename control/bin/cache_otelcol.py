#!/usr/bin/env python3
"""Cache and verify one pinned official otelcol-contrib artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
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


def _kept(destination: Path) -> str:
    return (
        f"The partial file was kept at {destination} and the next deploy continues it."
        if destination.exists()
        else "No partial file was left behind."
    )


def _download_urllib(url: str, destination: Path, timeout_seconds: int) -> None:
    # file:// fixtures and the rare host without aria2c. urlopen's timeout is an
    # idle timeout; the deploy's process-group window is what stops a stuck socket.
    request = urllib.request.Request(url, headers={"User-Agent": "stayturgid-otelcol-cache/1"})
    try:
        # bandit B310 (urlopen scheme audit) is a false positive: the URL is the pinned artifact
        # URL and the download is sha256-verified before use.
        with (
            urllib.request.urlopen(request, timeout=timeout_seconds) as response,  # nosemgrep  # nosec B310
            destination.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
    except (OSError, urllib.error.URLError) as exc:
        raise ArtifactError(f"download of {destination.name} failed. {_kept(destination)} {exc}") from exc


def _download_aria2(url: str, destination: Path, timeout_seconds: int) -> None:
    aria2c = shutil.which("aria2c")
    if aria2c is None:
        if destination.exists():
            raise ArtifactError(
                f"download of {destination.name} needs aria2c to continue the partial file at {destination}."
            )
        _download_urllib(url, destination, timeout_seconds)
        return
    cmd = [
        aria2c,
        "--continue=true",
        "--auto-file-renaming=false",
        "--max-connection-per-server=4",
        "--split=4",
        "--min-split-size=4M",
        "--max-tries=10",
        "--retry-wait=5",
        "--timeout=60",
        "--file-allocation=none",
        "--console-log-level=warn",
        "--summary-interval=0",
        "--dir",
        str(destination.parent),
        "--out",
        destination.name,
        url,
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise ArtifactError(
            f"download of {destination.name} did not finish within {timeout_seconds}s. "
            f"The transfer was stopped. {_kept(destination)}"
        ) from exc
    sidecar = Path(str(destination) + ".aria2")
    if completed.returncode != 0 or not destination.is_file() or sidecar.exists():
        detail = (completed.stderr or completed.stdout or f"aria2c exit {completed.returncode}").strip()
        raise ArtifactError(f"download of {destination.name} failed. {_kept(destination)} {detail[:500]}")


def download_to(url: str, destination: Path, timeout_seconds: int) -> None:
    """One transfer. A failure leaves destination in place so the next call resumes it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("file:"):
        _download_urllib(url, destination, timeout_seconds)
        return
    _download_aria2(url, destination, timeout_seconds)


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


def _download_window(timeout_seconds: int | None) -> int:
    if timeout_seconds is not None:
        return timeout_seconds
    raw = os.environ.get("STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS", "1800")
    try:
        window = int(raw)
    except ValueError as exc:
        raise ArtifactError(f"STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS is not an integer: {raw}") from exc
    if window <= 0:
        raise ArtifactError(f"download time window must be positive, got {window}")
    return window


def ensure_cached(
    *,
    url: str,
    expected_sha256: str,
    cache_dir: Path,
    architecture: str,
    timeout_seconds: int | None = None,
) -> bool:
    if architecture != "linux_arm64":
        raise ArtifactError(f"unsupported archive architecture: {architecture!r}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_name = Path(urllib.parse.urlparse(url).path).name
    if not archive_name:
        raise ArtifactError("artifact URL has no archive filename")
    archive = cache_dir / archive_name
    binary = cache_dir / "otelcol-contrib"
    window = _download_window(timeout_seconds)

    if archive.exists():
        verify_checksum(archive, expected_sha256)
    else:
        partial = cache_dir / f"{archive_name}.partial"
        download_to(url, partial, window)
        try:
            verify_checksum(partial, expected_sha256)
        except ArtifactError:
            # A finished file with the wrong bytes is not a transfer to resume.
            partial.unlink(missing_ok=True)
            Path(str(partial) + ".aria2").unlink(missing_ok=True)
            raise
        os.replace(partial, archive)

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
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Seconds the one download may take. Defaults to STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS or 1800.",
    )
    args = parser.parse_args(argv)
    try:
        changed = ensure_cached(
            url=args.url,
            expected_sha256=args.sha256,
            cache_dir=args.cache_dir.expanduser(),
            architecture=args.architecture,
            timeout_seconds=args.timeout,
        )
    except ArtifactError as exc:
        parser.error(str(exc))
    print(json.dumps({"binary": str(args.cache_dir / "otelcol-contrib"), "changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
