#!/usr/bin/env python3
"""Cache the latest official otelcol-contrib release archive on the Mac.

The newest release of open-telemetry/opentelemetry-collector-releases is
resolved from GitHub, its archive is downloaded once into
``<cache-root>/<version>/`` and the binary is unpacked next to it. Site policy
is to track the latest upstream release: no version or checksum is pinned. The
archive's gzip CRC and the AArch64 ELF check still reject a truncated or wrong
download.
"""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

RELEASES_REPO = "open-telemetry/opentelemetry-collector-releases"
_VERSION = re.compile(r"^[0-9]+(?:[.][0-9]+)+$")


class ArtifactError(RuntimeError):
    """The collector artifact failed a download, integrity, or architecture check."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _github_token() -> str:
    """GITHUB_TOKEN/GH_TOKEN, else the gh CLI login, else unauthenticated (60/hour per IP)."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    gh = shutil.which("gh")
    if gh is None:
        return ""
    try:
        done = subprocess.run([gh, "auth", "token"], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def resolve_latest_version(timeout_seconds: int = 30) -> str:
    """The newest published (non-draft, non-prerelease) collector release, without the leading v."""
    url = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "stayturgid-otelcol-cache/1"}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        # Fixed https GitHub API URL.
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosemgrep  # nosec B310
            tag = str(json.loads(response.read().decode("utf-8")).get("tag_name", ""))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ArtifactError(f"could not resolve the latest {RELEASES_REPO} release: {exc}") from exc
    version = tag.removeprefix("v")
    if not _VERSION.match(version):
        raise ArtifactError(f"latest {RELEASES_REPO} tag {tag!r} is not a dotted version")
    return version


def archive_name(version: str, architecture: str) -> str:
    return f"otelcol-contrib_{version}_{architecture}.tar.gz"


def archive_url(version: str, architecture: str) -> str:
    return f"https://github.com/{RELEASES_REPO}/releases/download/v{version}/{archive_name(version, architecture)}"


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
        # bandit B310 (urlopen scheme audit) is a false positive: the URL is the
        # collector release URL built by archive_url (or a file:// test fixture).
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


def _partial_started(destination: Path) -> bool:
    sidecar = Path(str(destination) + ".aria2")
    try:
        size = destination.stat().st_size
    except OSError:
        size = 0
    return size > 0 or sidecar.exists()


def download_to(url: str, destination: Path, timeout_seconds: int) -> None:
    """One transfer. A failure leaves destination in place so the next call resumes it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("file:"):
        _download_urllib(url, destination, timeout_seconds)
        return
    host = os.environ.get("STAYTURGID_FETCH_SSH_HOST", "").strip()
    window = timeout_seconds
    # A partial stays with aria2. The host path is only for a transfer that has
    # not started, and only when that host proves it is faster than 2 MiB/s.
    if host and not _partial_started(destination):
        started = time.monotonic()
        lib = str(Path(__file__).resolve().parents[1] / "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        from asset_fetch import FetchError, try_vps

        try:
            if try_vps(host, url, destination, timeout_seconds):
                return
        except FetchError as exc:
            raise ArtifactError(str(exc)) from exc
        window = int(timeout_seconds - (time.monotonic() - started))
        if window <= 0:
            raise ArtifactError(
                f"download of {destination.name} did not finish within {timeout_seconds}s. "
                f"The transfer was stopped. {_kept(destination)}"
            )
    _download_aria2(url, destination, window)


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
    except (OSError, EOFError, zlib.error, tarfile.TarError) as exc:
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
    except (OSError, EOFError, zlib.error, tarfile.TarError) as exc:
        raise ArtifactError(f"invalid collector archive: {exc}") from exc
    return digest.hexdigest()


def _verify_archive(archive: Path) -> None:
    """Decompress the whole gzip stream (its CRC and length trailer catch a
    truncated or corrupt transfer; tarfile stops reading at the last member),
    then require exactly one collector binary inside."""
    try:
        with gzip.open(archive, "rb") as stream:
            while stream.read(1024 * 1024):
                pass
    except (OSError, EOFError, zlib.error) as exc:
        raise ArtifactError(f"invalid collector archive: {exc}") from exc
    _archive_binary_sha256(archive)


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

    # One writer. A deploy and anything else caching this version wait, then reuse the file.
    lock_path = cache_dir / ".fetch.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not archive.exists():
            partial = cache_dir / f"{archive_name}.partial"
            download_to(url, partial, window)
            try:
                _verify_archive(partial)
            except ArtifactError:
                # A finished file with the wrong bytes is not a transfer to resume.
                partial.unlink(missing_ok=True)
                Path(str(partial) + ".aria2").unlink(missing_ok=True)
                raise
            os.replace(partial, archive)

        if binary.exists():
            validate_linux_arm64_elf(binary)
            if sha256_file(binary) != _archive_binary_sha256(archive):
                raise ArtifactError("cached otelcol-contrib binary does not match the cached archive")
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


def _prune_other_versions(cache_root: Path, keep: str) -> None:
    # Every release leaves ~0.5 GB (archive + unpacked binary); only the latest is ever deployed.
    for child in cache_root.iterdir():
        if child.is_dir() and child.name != keep and _VERSION.match(child.name):
            shutil.rmtree(child, ignore_errors=True)


def cache_latest(
    *,
    cache_root: Path,
    architecture: str,
    timeout_seconds: int | None = None,
    version: str | None = None,
) -> dict[str, object]:
    """Cache the latest release (or ``version``, already resolved by the caller) under cache_root/<version>/."""
    version = version or resolve_latest_version()
    cache_dir = cache_root / version
    changed = ensure_cached(
        url=archive_url(version, architecture),
        cache_dir=cache_dir,
        architecture=architecture,
        timeout_seconds=timeout_seconds,
    )
    _prune_other_versions(cache_root, version)
    return {
        "version": version,
        "archive": str(cache_dir / archive_name(version, architecture)),
        "binary": str(cache_dir / "otelcol-contrib"),
        "changed": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Seconds the one download may take. Defaults to STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS or 1800.",
    )
    args = parser.parse_args(argv)
    try:
        result = cache_latest(
            cache_root=args.cache_root.expanduser(),
            architecture=args.architecture,
            timeout_seconds=args.timeout,
        )
    except ArtifactError as exc:
        parser.error(str(exc))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
